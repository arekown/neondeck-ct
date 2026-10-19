"""Modus „Simulieren“: Klicks und Mausrad am Geraetebild gehen als Geraete-Ereignisse an den Dienst."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from neondeck.device.layout import ControlRef
from neondeck.device.protocol import ButtonEvent, RotateEvent, TouchEvent
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def test_simulate_sends_events(editor_service, editor, monkeypatch):
    events = []
    real = editor_service.app.engine.handle
    monkeypatch.setattr(editor_service.app.engine, "handle",
                        lambda ev: (events.append(ev), real(ev)))
    win = editor.window
    view = win.device_view
    win.select(ControlRef("square", 2))
    sim = win.simulator
    sim.button.click()
    assert sim.active and sim.button.isChecked() and view.simulating
    assert win.simulate_label.isVisibleTo(win)

    def click(ref):
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=view.control_rect(ref).center())

    click(ControlRef("touch", 5))
    assert wait_until(lambda: len(events) == 2)
    down, up = events
    assert isinstance(down, TouchEvent) and down.down and not up.down
    assert 60 + 90 <= down.x < 60 + 180 and 90 <= down.y < 180  # Feld 6 (Zeile 2, Spalte 2)
    click(ControlRef("round", 0))
    assert wait_until(lambda: len(events) == 4)
    assert events[2:] == [ButtonEvent(7, True), ButtonEvent(7, False)]
    pos = QPointF(view.control_rect(ControlRef("knob", 1)).center())
    wheel = QWheelEvent(pos, QPointF(view.mapToGlobal(pos.toPoint())), QPoint(),
                        QPoint(0, 240), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, wheel)
    assert wait_until(lambda: len(events) == 6)
    assert events[4:] == [RotateEvent(2, 1), RotateEvent(2, 1)]
    assert win.selected == ControlRef("square", 2)  # Simulieren waehlt nichts aus

    sim.button.click()
    assert not sim.active and not view.simulating and not win.simulate_label.isVisibleTo(win)
    click(ControlRef("round", 1))
    QApplication.processEvents()
    assert win.selected == ControlRef("round", 1) and len(events) == 6
