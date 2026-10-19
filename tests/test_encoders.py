"""Regler und Rad frei belegbar (P9): Richtung/Faktor, links/rechts, Ebenen, Leiste, Rad."""
import pytest

from neondeck.actions.base import Result
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent, RotateEvent, TouchEvent, WheelTouchEvent
from neondeck.engine.encoders import MAX_REPEAT
from neondeck.profile.model import ButtonImage, Encoder, EncoderLayer
from neondeck.render.images import (
    WHEEL_TILE,
    TileSpec,
    render_strip,
    render_wheel,
    to_rgb565,
    wheel_tile,
)
from support.engine_rig import Rig, make_profile, make_rig

K0 = ControlRef("knob", 0)
WHEEL = ControlRef("wheel", 0)
LEFT = {"type": "hotkey", "keys": ["KEY_LEFT"]}
RIGHT = {"type": "hotkey", "keys": ["KEY_RIGHT"]}
TAP = {"type": "run", "command": "rad-tippen"}


def last_bytes(rig, display):
    return next(b for d, b in reversed(rig.draws) if d is display)


def layered(**kw):
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(layers=[
        EncoderLayer(rotate={"type": "volume"}, press={"type": "mute_toggle"}, label="Laut"),
        EncoderLayer(rotate={"type": "brightness"}, press={"type": "brightness_reset"},
                     label="Hell")], **kw)
    return p


def click(rig, code=1):
    rig.engine.handle(ButtonEvent(code, True))
    rig.engine.handle(ButtonEvent(code, False))


# --- Drehen: Richtung, Faktor, links/rechts ---------------------------------------------

def test_invert_and_factor():
    p = make_profile()
    p.workspaces[0].encoders[0].invert = True
    p.workspaces[0].encoders[0].factor = 3
    rig = Rig(p)
    rig.engine.handle(RotateEvent(1, +1))
    assert [(c[0], c[2]) for c in rig.ex.calls] == [(K0, -3)]
    rig.engine.handle(RotateEvent(1, +1))   # laeuft noch: sammeln
    rig.engine.handle(RotateEvent(1, +1))
    rig.ex.finish()
    assert [c[2] for c in rig.ex.calls] == [-3, -6]


def test_wheel_invert_and_factor():
    p = make_profile()
    w = p.workspaces[0].wheel
    w.rotate, w.invert, w.factor = {"type": "volume"}, True, 2
    rig = Rig(p)
    rig.engine.handle(RotateEvent(0, -1))
    assert [(c[0], c[2]) for c in rig.ex.calls] == [(WHEEL, 2)]


def test_left_right_actions():
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(left=LEFT, right=RIGHT, factor=2)
    rig = Rig(p)
    rig.engine.handle(RotateEvent(1, +1))
    assert [(c[0], c[1], c[2]) for c in rig.ex.calls] == [(K0, RIGHT, 0), (K0, RIGHT, 0)]
    rig.engine.handle(RotateEvent(1, -1))   # laeuft noch (zwei offen): sammeln
    rig.ex.finish()
    assert len(rig.ex.calls) == 2           # erst nach dem letzten Ergebnis weiter
    rig.ex.finish()
    assert [c[1] for c in rig.ex.calls[2:]] == [LEFT, LEFT]


def test_left_right_capped_per_flush():
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(left=LEFT, right=RIGHT, factor=10)
    rig = Rig(p)
    rig.engine.handle(RotateEvent(1, +1))   # 10 Schritte
    rig.engine.handle(RotateEvent(1, +1))   # gesammelt ...
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.handle(RotateEvent(1, +1))
    while rig.ex.open[:-1]:
        rig.ex.finish()
    rig.ex.finish()                         # ... 30 Schritte: hoechstens MAX_REPEAT
    assert len(rig.ex.calls) == 10 + MAX_REPEAT
    while rig.ex.open:
        rig.ex.finish()
    assert len(rig.ex.calls) == 10 + MAX_REPEAT  # Rest verworfen, keine Flut


def test_missing_direction_falls_back_to_rotate():
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(rotate={"type": "volume"}, right=RIGHT)
    rig = Rig(p)
    rig.engine.handle(RotateEvent(1, -1))
    assert [(c[1], c[2]) for c in rig.ex.calls] == [({"type": "volume"}, -1)]


def test_wheel_left_right():
    p = make_profile()
    p.workspaces[0].wheel.left, p.workspaces[0].wheel.right = LEFT, RIGHT
    rig = Rig(p)
    rig.engine.handle(RotateEvent(0, -1))
    assert [(c[0], c[1], c[2]) for c in rig.ex.calls] == [(WHEEL, LEFT, 0)]


def test_api_rotate_uses_direction_and_factor():
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(left=LEFT, right=RIGHT, invert=True)
    rig = Rig(p)
    assert rig.engine.activate(K0, "rotate", steps=2)
    assert [c[1] for c in rig.ex.calls] == [LEFT, LEFT]


# --- Ebenen ------------------------------------------------------------------------------

def test_layers_press_switches_rotate_uses_layer():
    rig = make_rig(layered())
    rig.engine.handle(RotateEvent(1, +1))
    rig.timers.advance(0.05)
    assert rig.ex.calls[-1][1] == {"type": "volume"}
    rig.ex.finish()
    assert rig.engine.painter.strip_label(0) == "Laut"
    click(rig)                              # kurzes Druecken: naechste Ebene, nichts ausfuehren
    assert len(rig.ex.calls) == 1
    assert rig.engine.painter.strip_label(0) == "Ebene 2/2 · Hell"
    rig.engine.handle(RotateEvent(1, +1))
    rig.timers.advance(0.05)
    assert rig.ex.calls[-1][1] == {"type": "brightness"}
    rig.timers.advance(2.0)
    assert rig.engine.painter.strip_label(0) == "Hell"
    click(rig)                              # zyklisch zurueck zu Ebene 1
    assert rig.engine.painter.strip_label(0) == "Ebene 1/2 · Laut"


def test_layer_kept_per_workspace():
    p = layered()
    rig = make_rig(p)
    click(rig)
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("workspace", {"id": "ws1"})
    rig.timers.advance(2.5)
    assert rig.engine.painter.strip_label(0) == "Hell"


def test_layer_hold_runs_press():
    rig = make_rig(layered())
    rig.engine.handle(ButtonEvent(1, True))
    rig.timers.advance(0.49)
    assert rig.ex.calls == []
    rig.timers.advance(0.02)                # hold_ms (500) erreicht: press der Ebene
    assert [c[:2] for c in rig.ex.calls] == [(K0, {"type": "mute_toggle"})]
    rig.engine.handle(ButtonEvent(1, False))
    assert rig.engine.painter.strip_label(0) == "Laut"  # Halten wechselt keine Ebene
    assert len(rig.ex.calls) == 1


def test_layer_hold_on_strip_touch_and_respects_hold_ms():
    rig = make_rig(layered(), hold_ms=800)
    rig.engine.handle(TouchEvent(1, 30, 45, True))   # Leiste links, Regler 0
    rig.timers.advance(0.6)
    assert rig.ex.calls == []
    rig.timers.advance(0.3)
    assert [c[1] for c in rig.ex.calls] == [{"type": "mute_toggle"}]
    rig.engine.handle(TouchEvent(1, 30, 45, False))
    rig.engine.handle(TouchEvent(1, 30, 45, True))   # kurz: Ebene wechseln
    rig.engine.handle(TouchEvent(1, 30, 45, False))
    assert rig.engine.painter.strip_label(0) == "Ebene 2/2 · Hell"


def test_layer_hold_without_timer_uses_duration():
    mono = [0.0]
    rig = Rig(layered(), monotonic=lambda: mono[0])
    rig.engine.handle(ButtonEvent(1, True))
    mono[0] = 0.6
    rig.engine.handle(ButtonEvent(1, False))
    assert [c[1] for c in rig.ex.calls] == [{"type": "mute_toggle"}]
    rig.engine.handle(ButtonEvent(1, True))
    rig.engine.handle(ButtonEvent(1, False))
    assert len(rig.ex.calls) == 1 and rig.engine.painter.strip_label(0) == "Ebene 2/2 · Hell"


def test_layer_hold_dropped_on_view_change():
    rig = make_rig(layered())
    rig.engine.handle(ButtonEvent(1, True))
    rig.engine.call("workspace", {"id": "ws2"})
    rig.timers.advance(1.0)
    rig.engine.handle(ButtonEvent(1, False))
    assert rig.ex.calls == []
    rig.engine.call("workspace", {"id": "ws1"})
    assert rig.engine.painter.strip_label(0) == "Laut"  # kein Ebenenwechsel nachgeholt


def test_api_tap_on_layered_knob_switches_layer_hold_runs_press():
    rig = make_rig(layered())
    assert rig.engine.activate(K0, "tap")
    assert rig.ex.calls == [] and rig.engine.painter.strip_label(0) == "Ebene 2/2 · Hell"
    assert rig.engine.activate(K0, "hold")
    assert rig.ex.calls[-1][1] == {"type": "brightness_reset"}


# --- Leiste -------------------------------------------------------------------------------

def test_strip_bar_mode():
    p = make_profile()
    p.workspaces[0].encoders[0].strip = "bar"
    p.workspaces[0].encoders[1].strip = "name"
    rig = Rig(p)
    rig.engine.redraw_all()
    rig.engine.handle(RotateEvent(1, +1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    expected = render_strip([("Lautstärke", None), ("Helligkeit", None), ("", None)],
                            bars=[42.0, None, None])
    assert last_bytes(rig, Display.LEFT) == to_rgb565(expected)
    rig.engine.handle(RotateEvent(1, +1))    # kein Prozentwert: wie name_value
    rig.ex.finish(result=Result(True, "stumm", muted=True))
    expected = render_strip([("Lautstärke", "stumm"), ("Helligkeit", None), ("", None)])
    assert last_bytes(rig, Display.LEFT) == to_rgb565(expected)
    rig.engine.handle(RotateEvent(2, +1))    # Modus name: nie ein Wert
    rig.ex.finish(result=Result(True, "80 %", value=80.0))
    expected = render_strip([("Lautstärke", "stumm"), ("Helligkeit", None), ("", None)])
    assert last_bytes(rig, Display.LEFT) == to_rgb565(expected)


# --- Rad ----------------------------------------------------------------------------------

def wheel_profile(display="arc"):
    p = make_profile()
    w = p.workspaces[0].wheel
    w.display, w.rotate, w.tap, w.label = display, {"type": "volume"}, TAP, "Laut"
    return p


def test_wheel_arc_and_tap():
    mono = [100.0]
    rig = Rig(wheel_profile(), monotonic=lambda: mono[0])
    rig.engine.redraw_all()
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(render_wheel("arc", "Laut"), True)
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    arc42 = to_rgb565(render_wheel("arc", "Laut", value=42.0), True)
    assert last_bytes(rig, Display.WHEEL) == arc42
    rig.clock.t += 5
    rig.engine.tick()                        # bleibt stehen (kein Ablauf wie die Leiste)
    assert last_bytes(rig, Display.WHEEL) == arc42
    # Tippen auf die Mitte
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))
    mono[0] += 0.1
    rig.engine.handle(WheelTouchEvent(1, 130, 125, True))  # leichtes Ziehen
    rig.engine.handle(WheelTouchEvent(1, 130, 125, False))
    assert rig.ex.calls[-1][:2] == (WHEEL, TAP)
    n = len(rig.ex.calls)
    # zu lang, ausserhalb der Mitte, zu weit gezogen: nichts
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))
    mono[0] += 0.35
    rig.engine.handle(WheelTouchEvent(1, 120, 120, False))
    rig.engine.handle(WheelTouchEvent(1, 190, 120, True))
    rig.engine.handle(WheelTouchEvent(1, 190, 120, False))
    rig.engine.handle(WheelTouchEvent(1, 110, 120, True))
    rig.engine.handle(WheelTouchEvent(1, 140, 120, True))
    rig.engine.handle(WheelTouchEvent(1, 120, 120, False))
    assert len(rig.ex.calls) == n


def test_wheel_tap_respects_lock_sleep_and_view_change():
    mono = [100.0]
    rig = Rig(wheel_profile(), monotonic=lambda: mono[0])
    rig.engine.lock()
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))
    rig.engine.handle(WheelTouchEvent(1, 120, 120, False))
    rig.engine.unlock()
    assert rig.ex.calls == []
    rig.engine.power.sleep_display()
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))    # weckt nur
    mono[0] += 1.0                                            # auch nach der Gnadenfrist:
    rig.engine.handle(WheelTouchEvent(1, 121, 120, True))    # Rest der Weck-Geste
    rig.engine.handle(WheelTouchEvent(1, 121, 120, False))
    assert rig.ex.calls == [] and not rig.engine.display_asleep
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))
    rig.engine.call("workspace", {"id": "ws2"})               # R25: Ansicht gewechselt
    rig.engine.call("workspace", {"id": "ws1"})
    rig.engine.handle(WheelTouchEvent(1, 120, 120, False))
    assert rig.ex.calls == []


def test_wheel_image_mode():
    p = wheel_profile("image")
    p.workspaces[0].wheel.image = ButtonImage(bg="#203040", text="Rad")
    rig = Rig(p)
    rig.engine.redraw_all()
    tile = wheel_tile(TileSpec("#203040", None, "Rad", "#ffffff"))
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(render_wheel("image", image=tile), True)


def test_wheel_image_icon_loaded_at_wheel_size():
    from PIL import Image
    sizes = []

    def loader(ref, size):
        sizes.append((ref, size))
        return Image.new("RGBA", (size, size), (255, 0, 0, 255))

    p = wheel_profile("image")
    p.workspaces[0].wheel.image = ButtonImage(icon="lib:rad.svg")
    rig = Rig(p, icon_loader=loader)
    rig.engine.redraw_all()
    assert ("lib:rad.svg", WHEEL_TILE) in sizes
    assert rig.last(Display.WHEEL)[120, 120].tolist() == [0xF8, 0, 0]


def test_wheel_value_cleared_on_workspace_change():
    rig = Rig(wheel_profile())
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("workspace", {"id": "ws1"})
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(render_wheel("arc", "Laut"), True)


@pytest.mark.parametrize("mode", ["clock", "label", "blank"])
def test_wheel_other_modes_unchanged(mode):
    from datetime import datetime
    rig = Rig(wheel_profile(mode))
    rig.engine.redraw_all()
    expected = render_wheel(mode, "Laut", datetime.fromtimestamp(rig.clock.t))
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(expected, True)


# --- Nacharbeit R30 -------------------------------------------------------------------------

def test_dropped_steps_are_logged(caplog):
    import logging
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(left=LEFT, right=RIGHT, factor=10)
    rig = Rig(p)
    with caplog.at_level(logging.INFO, logger="neondeck.engine.encoders"):
        rig.engine.handle(RotateEvent(1, +1))       # 10: nichts verworfen
        assert not caplog.records
        for _ in range(3):
            rig.engine.handle(RotateEvent(1, +1))
        while rig.ex.open:
            rig.ex.finish()
    assert any("10" in r.getMessage() for r in caplog.records)  # 30 - 20 verworfen


def test_rotate_while_layered_knob_down_cancels_hold_and_cycle():
    rig = make_rig(layered())
    rig.engine.handle(ButtonEvent(1, True))
    rig.engine.handle(RotateEvent(1, +1))           # gedrueckt drehen: Drehen gilt ...
    rig.timers.advance(0.6)                         # ... aber kein Halten
    assert [c[1] for c in rig.ex.calls] == [{"type": "volume"}]
    rig.engine.handle(ButtonEvent(1, False))        # ... und kein Ebenenwechsel
    assert rig.engine.painter.strip_label(0) == "Laut"
    assert len(rig.ex.calls) == 1
    click(rig)                                      # danach wieder normal
    assert rig.engine.painter.strip_label(0) == "Ebene 2/2 · Hell"


def test_wheel_arc_keeps_last_percent_and_shows_muted():
    rig = Rig(wheel_profile())
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "irgendeine Ausgabe"))   # kein Prozentwert: bleibt
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(
        render_wheel("arc", "Laut", value=42.0), True)
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "stumm", muted=True))
    muted = to_rgb565(render_wheel("arc", "Laut", value=42.0, muted=True), True)
    assert last_bytes(rig, Display.WHEEL) == muted
    assert muted != to_rgb565(render_wheel("arc", "Laut", value=42.0), True)
    rig.engine.handle(RotateEvent(0, +1))
    rig.ex.finish(result=Result(True, "45 %", value=45.0))                 # wieder laut
    assert last_bytes(rig, Display.WHEEL) == to_rgb565(
        render_wheel("arc", "Laut", value=45.0), True)


def test_wheel_tap_ignored_with_second_finger_and_stale_touch_expires():
    mono = [100.0]
    rig = Rig(wheel_profile(), monotonic=lambda: mono[0])
    rig.engine.handle(WheelTouchEvent(1, 120, 120, True))
    rig.engine.handle(WheelTouchEvent(2, 125, 120, True))   # zweiter Finger
    rig.engine.handle(WheelTouchEvent(2, 125, 120, False))
    rig.engine.handle(WheelTouchEvent(1, 120, 120, False))
    assert rig.ex.calls == []
    rig.engine.handle(WheelTouchEvent(3, 120, 120, True))   # Abheben geht verloren
    mono[0] += 2.5
    rig.engine.handle(WheelTouchEvent(4, 120, 120, True))   # veraltet: zaehlt nicht mit
    rig.engine.handle(WheelTouchEvent(4, 120, 120, False))
    assert [c[:2] for c in rig.ex.calls] == [(WHEEL, TAP)]


def test_editor_save_shrinking_layers_keeps_valid_index():
    p = layered()
    p.workspaces[0].encoders[0].layers.append(
        EncoderLayer(rotate={"type": "volume"}, label="Drei"))
    rig = make_rig(p)
    click(rig)
    click(rig)                                      # Ebene 3/3
    rig.timers.advance(2.5)
    assert rig.engine.painter.strip_label(0) == "Drei"
    rig.engine.set_profile(layered(), keep_view=True)   # nur noch 2 Ebenen
    assert rig.engine.painter.strip_label(0) in ("Laut", "Hell")
    rig.engine.handle(RotateEvent(1, +1))
    rig.timers.advance(0.05)
    assert rig.ex.calls[-1][1] in ({"type": "volume"}, {"type": "brightness"})
    click(rig)
    assert rig.engine.painter.strip_label(0).startswith("Ebene ")
    assert "/2 · " in rig.engine.painter.strip_label(0)


def test_left_right_mixed_burst_runs_net_direction():
    p = make_profile()
    p.workspaces[0].encoders[0] = Encoder(left=LEFT, right=RIGHT)
    rig = Rig(p)
    rig.engine.handle(RotateEvent(1, +1))           # laeuft
    for d in (+1, -1, -1, +1, -1, -1):              # netto -2
        rig.engine.handle(RotateEvent(1, d))
    rig.ex.finish()
    assert [c[1] for c in rig.ex.calls] == [RIGHT, LEFT, LEFT]
