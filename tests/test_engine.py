import numpy as np
import pytest

from neondeck.actions.base import Result
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent, RotateEvent, TouchEvent, WheelTouchEvent
from neondeck.engine.leds import LED_ACTIVE, LED_DIM, LED_OFF
from neondeck.engine.ports import EnginePorts
from neondeck.profile.model import Assignment, ButtonImage, Encoder, TouchPage
from support.engine_rig import TILE5, Rig, make_engine, make_profile, pixels
from support.fakes import FakeExecutor

RED = (0xF8, 0x20, 0x20)  # #ff2020 nach RGB565


# --- Touch -------------------------------------------------------------------

def test_touch_tap_executes_button():
    rig = Rig()
    rig.tap(*TILE5)
    assert len(rig.ex.calls) == 1
    ref, action, steps, pressed = rig.ex.calls[0]
    assert ref == ControlRef("touch", 5) and action["command"] == "firefox" and pressed


def test_touch_down_highlights_tile_white():
    rig = Rig()
    rig.engine.redraw_all()
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) == (0xF8, 0xFC, 0xF8)
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) == (0, 0, 0)


def test_touch_up_on_other_field_does_nothing():
    rig = Rig()
    rig.tap(*TILE5, x_up=TILE5[0] + 90)  # 90 px: kein Wischen, aber anderes Feld
    assert rig.ex.calls == []


def test_touch_swipe_changes_page():
    p = make_profile()
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = Rig(p)
    rig.engine.redraw_all()
    before = rig.count(Display.CENTER)
    rig.tap(100, 135, x_up=300)
    assert rig.engine.page_index == 1
    assert rig.ex.calls == []
    assert rig.count(Display.CENTER) == before + 1
    rig.tap(300, 135, x_up=100)  # Gegenrichtung zurueck
    assert rig.engine.page_index == 0


def test_strip_touch_is_knob_press():
    rig = Rig()
    rig.tap(30, 135)
    ref, action, steps, pressed = rig.ex.calls[0]
    assert ref == ControlRef("knob", 1) and action == {"type": "brightness_reset"}
    assert steps == 0 and pressed
    assert len(rig.ex.calls) == 1  # Loslassen geht nur an hold_key


def test_right_strip_maps_to_encoders_3_to_5():
    p = make_profile()
    p.workspaces[0].encoders[5] = Encoder(press={"type": "mute_toggle"})
    rig = Rig(p)
    rig.tap(450, 250)
    assert rig.ex.calls[0][0] == ControlRef("knob", 5)


def test_wheel_touch_without_tap_does_nothing():
    rig = Rig()
    rig.engine.handle(WheelTouchEvent(1, 100, 100, True))
    assert rig.ex.calls == []


# --- Tasten --------------------------------------------------------------------

def test_round_button_switches_workspace_and_leds():
    rig = Rig()
    rig.engine.redraw_all()
    other_ws = (51, 51, 51)  # anderer Arbeitsbereich: seine Farbe (Standard weiss) mit 20 %
    assert rig.leds[-1][7] == LED_ACTIVE and rig.leds[-1][8] == other_ws
    rig.engine.handle(ButtonEvent(8, True))
    rig.engine.handle(ButtonEvent(8, False))
    assert rig.engine.workspace_id == "ws2"
    leds = rig.leds[-1]
    assert leds[8] == LED_ACTIVE
    assert leds[7] == other_ws and leds[9] == LED_DIM  # belegt, aber nicht aktiv
    assert leds[10] == LED_OFF and set(leds) == set(range(7, 15))
    assert rig.ex.calls == []  # Navigation laeuft direkt in der Engine


def test_unknown_button_code_ignored():
    rig = Rig()
    rig.engine.handle(ButtonEvent(99, True))
    assert rig.ex.calls == []


def test_knob_button_press():
    rig = Rig()
    rig.engine.handle(ButtonEvent(1, True))
    rig.engine.handle(ButtonEvent(1, False))
    assert [c[:2] for c in rig.ex.calls] == [(ControlRef("knob", 0), {"type": "mute_toggle"})]


def test_hold_key_gets_release_other_press_actions_do_not():
    p = make_profile()
    p.square[15] = Assignment({"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]})
    rig = Rig(p)
    rig.engine.handle(ButtonEvent(15, True))
    rig.engine.handle(ButtonEvent(15, False))
    rig.engine.handle(ButtonEvent(9, True))   # hotkey
    rig.engine.handle(ButtonEvent(9, False))
    assert [(c[0], c[3]) for c in rig.ex.calls] == [
        (ControlRef("square", 0), True), (ControlRef("square", 0), False),
        (ControlRef("round", 2), True)]


def test_shutdown_releases_held_keys():
    p = make_profile()
    p.square[16] = Assignment({"type": "hold_key", "keys": ["KEY_LEFTCTRL"]})
    rig = Rig(p)
    rig.engine.handle(ButtonEvent(16, True))
    rig.engine.shutdown()
    assert rig.ex.calls[-1][0] == ControlRef("square", 2) and rig.ex.calls[-1][3] is False
    assert rig.ex.shut


def test_hold_key_release_after_workspace_switch_uses_pressed_action():
    p = make_profile()
    p.workspaces[0].encoders[2] = Encoder(press={"type": "hold_key", "keys": ["KEY_LEFTALT"]})
    rig = Rig(p)
    rig.engine.handle(ButtonEvent(3, True))
    rig.engine.handle(ButtonEvent(8, True))  # Arbeitsbereich wechseln, Regler 2 dort leer
    rig.engine.handle(ButtonEvent(3, False))
    assert rig.ex.calls[-1][1]["keys"] == ["KEY_LEFTALT"] and rig.ex.calls[-1][3] is False


# --- Drehen ----------------------------------------------------------------------

def test_rotate_coalesced():
    """Review Focus 5: 50 schnelle Drehungen -> hoechstens zwei Ausfuehrungen."""
    rig = Rig()
    for _ in range(50):
        rig.engine.handle(RotateEvent(1, +1))
    assert 1 <= len(rig.ex.calls) <= 2
    while rig.ex.open:
        rig.ex.finish()
    assert 1 <= len(rig.ex.calls) <= 2
    assert sum(c[2] for c in rig.ex.calls) == 50
    assert all(c[0] == ControlRef("knob", 0) and c[1] == {"type": "volume"} for c in rig.ex.calls)


def test_rotate_window_collects_into_one_call():
    later = []
    rig = Rig(call_later=lambda delay, fn: later.append((delay, fn)))
    for _ in range(30):
        rig.engine.handle(RotateEvent(2, -1))
    assert rig.ex.calls == []
    rot = [x for x in later if x[0] == pytest.approx(0.03)]
    assert len(rot) == 1
    rot[0][1]()
    assert [(c[0], c[2]) for c in rig.ex.calls] == [(ControlRef("knob", 1), -30)]


def test_rotate_while_running_keeps_collecting():
    rig = Rig()
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.handle(RotateEvent(1, -1))
    rig.engine.handle(RotateEvent(1, +1))
    assert [c[2] for c in rig.ex.calls] == [1]
    rig.ex.finish()
    assert [c[2] for c in rig.ex.calls] == [1, 1]
    rig.ex.finish()
    assert len(rig.ex.calls) == 2  # nichts mehr offen


def test_hanging_action_does_not_block_other_controls():
    """Review Focus 2: haengt eine Aktion, reagieren andere Bedienelemente weiter."""
    rig = Rig()
    rig.engine.handle(RotateEvent(1, +1))           # haengt (nie beendet)
    rig.engine.handle(RotateEvent(2, +1))
    rig.tap(*TILE5)
    assert [c[0] for c in rig.ex.calls] == [ControlRef("knob", 0), ControlRef("knob", 1),
                                             ControlRef("touch", 5)]


def test_wheel_rotate():
    p = make_profile()
    p.workspaces[0].wheel.rotate = {"type": "volume"}
    rig = Rig(p)
    rig.engine.handle(RotateEvent(0, -1))
    assert rig.ex.calls[0][0] == ControlRef("wheel", 0) and rig.ex.calls[0][2] == -1


# --- Ergebnisse -----------------------------------------------------------------

def test_error_flashes_red():
    """Review Focus 4: Fehler -> 600 ms roter Rand an der Kachel."""
    later = []
    rig = Rig(call_later=lambda d, fn: later.append((d, fn)))
    rig.engine.redraw_all()
    rig.tap(*TILE5)
    rig.ex.finish(result=Result(False, "firefox nicht gefunden"))
    img = rig.last(Display.CENTER)
    assert tuple(img[90 + 45, 90 + 1]) == RED      # linker Rand von Feld 5
    assert tuple(img[90 + 45, 1]) != RED           # Feld 4 nicht
    assert rig.status and "firefox nicht gefunden" in rig.status[-1]
    rig.clock.t += 0.3
    rig.engine.tick()
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) == RED
    rig.clock.t += 0.3
    for d, fn in later:
        if d == pytest.approx(0.6):
            fn()
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) != RED


def test_error_on_knob_flashes_strip_section():
    rig = Rig()
    rig.engine.redraw_all()
    rig.engine.handle(RotateEvent(2, +1))
    rig.ex.finish(result=Result(False, "ddcutil nicht installiert"))
    img = rig.last(Display.LEFT)
    assert tuple(img[90 + 45, 1]) == RED and tuple(img[45, 1]) != RED
    rig.clock.t += 0.6
    rig.engine.tick()
    assert tuple(rig.last(Display.LEFT)[90 + 45, 1]) != RED


def test_volume_message_on_strip():
    rig = Rig()
    rig.engine.redraw_all()
    blank = rig.last(Display.LEFT).copy()
    n_left, n_center = rig.count(Display.LEFT), rig.count(Display.CENTER)
    rig.engine.handle(RotateEvent(1, +1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    assert rig.count(Display.LEFT) == n_left + 1
    assert rig.count(Display.CENTER) == n_center  # nur die geaenderte Anzeige
    with_value = rig.last(Display.LEFT)
    assert not np.array_equal(with_value[:90], blank[:90])
    assert np.array_equal(with_value[90:], blank[90:])
    rig.clock.t += 2.0
    rig.engine.tick()
    assert np.array_equal(rig.last(Display.LEFT), blank)


def test_results_are_posted_to_engine_thread():
    queued = []
    rig = Rig(post=queued.append)
    rig.engine.redraw_all()
    n = rig.count(Display.LEFT)
    rig.engine.handle(RotateEvent(1, +1))
    rig.ex.finish(result=Result(True, "50 %", value=50.0))
    assert rig.count(Display.LEFT) == n  # noch nicht angewendet
    for fn in queued:
        fn()
    assert rig.count(Display.LEFT) == n + 1


def test_engine_call_from_worker_is_posted():
    queued = []
    rig = Rig(post=queued.append)
    rig.ex.engine_call("workspace", {"id": "ws2"})
    assert rig.engine.workspace_id == "ws1"
    for fn in queued:
        fn()
    assert rig.engine.workspace_id == "ws2"


# --- Navigation und Profile ------------------------------------------------------

def test_call_navigation():
    p = make_profile()
    p.workspaces[0].touch_pages += [TouchPage("p2", "2"), TouchPage("p3", "3")]
    profiles = []
    rig = Rig(p, on_profile=profiles.append)
    e = rig.engine
    e.call("page", {"index": 2})
    assert e.page_index == 2
    e.call("page_next", {})
    assert e.page_index == 0
    e.call("page_previous", {})
    assert e.page_index == 2
    e.call("page", {"index": 7})
    assert e.page_index == 2
    e.call("workspace", {"id": "gibtsnicht"})
    assert e.workspace_id == "ws1"
    e.call("workspace", {"id": "ws2"})
    assert e.workspace_id == "ws2" and e.page_index == 0
    e.call("open_config", {})
    assert rig.opened == [True]
    e.call("profile", {"id": "spiel"})
    assert profiles == ["spiel"]


def test_set_profile_resets_to_home_workspace():
    rig = Rig()
    rig.engine.call("workspace", {"id": "ws2"})
    p = make_profile()
    p.home_workspace = "ws2"
    n = len(rig.draws)
    rig.engine.set_profile(p)
    assert rig.engine.profile is p
    assert rig.engine.workspace_id == "ws2" and rig.engine.page_index == 0
    assert {d for d, _ in rig.draws[n:]} == set(Display)


# --- Zeichnen ----------------------------------------------------------------------

def test_redraw_all_draws_every_display_even_unchanged():
    """Review Focus 1: nach Wiederverbinden alles neu zeichnen."""
    rig = Rig()
    rig.engine.redraw_all()
    rig.engine.redraw_all()
    assert [d for d, _ in rig.draws] == list(Display) * 2
    assert len(rig.leds) == 2
    assert all(len(b) == d.width * d.height * 2 for d, b in rig.draws)


def test_draw_failure_does_not_raise():
    p = make_profile()

    def broken(display, data):
        raise OSError("getrennt")

    e = make_engine(p, broken, executor_factory=FakeExecutor)
    e.redraw_all()
    e.handle(ButtonEvent(8, True))
    assert e.workspace_id == "ws2"


def test_tile_without_icon_and_text_shows_action_label():
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[0] = Assignment({"type": "kde", "name": "emoji"})
    rig = Rig(p)
    rig.engine.redraw_all()
    tile = rig.last(Display.CENTER)[0:90, 0:90]
    assert tile.any()


def test_tick_redraws_live_tile_only_when_text_changes():
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[0] = Assignment({"type": "clock"})
    rig = Rig(p)
    rig.clock.t = 1_760_000_040.0  # :00 Sekunden einer Minute
    rig.engine.redraw_all()
    n = rig.count(Display.CENTER)
    rig.clock.t += 1
    rig.engine.tick()
    assert rig.count(Display.CENTER) == n
    rig.engine.tick(rig.clock.t + 60)
    assert rig.count(Display.CENTER) == n + 1


def test_stopwatch_on_touch_tile():
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[0] = Assignment({"type": "stopwatch"})
    rig = Rig(p)
    rig.engine.redraw_all()
    rig.tap(105, 45)   # kurz: starten
    assert rig.ex.calls == []
    first = rig.last(Display.CENTER)[0:90, 0:90].copy()
    rig.clock.t += 5
    rig.engine.tick()
    assert not np.array_equal(rig.last(Display.CENTER)[0:90, 0:90], first)
    # lang druecken (> 1 s): zuruecksetzen
    rig.engine.handle(TouchEvent(1, 105, 45, True))
    rig.clock.t += 1.5
    rig.engine.handle(TouchEvent(1, 105, 45, False))
    assert np.array_equal(rig.last(Display.CENTER)[0:90, 0:90], first)


def test_wheel_modes():
    p = make_profile()
    p.workspaces[0].wheel.display = "clock"
    rig = Rig(p)
    rig.engine.redraw_all()
    assert rig.last(Display.WHEEL).any()
    n = rig.count(Display.WHEEL)
    rig.clock.t += 1
    rig.engine.tick()
    assert rig.count(Display.WHEEL) == n + 1
    rig.engine.call("workspace", {"id": "ws2"})  # Rad-Text "ZWEI"
    assert rig.last(Display.WHEEL).any()
    n = rig.count(Display.WHEEL)
    rig.clock.t += 1
    rig.engine.tick()
    assert rig.count(Display.WHEEL) == n  # Text aendert sich nicht


def test_strip_labels_from_encoder_or_action():
    p = make_profile()
    rig = Rig(p)
    rig.engine.redraw_all()
    left = rig.last(Display.LEFT)
    assert left[0:90].any() and left[90:180].any()   # "Lautstärke", "Helligkeit"
    assert not left[182:].any()                      # Regler 2 leer (unter der Trennlinie)


def test_synchronous_executor_does_not_stick_rotation():
    """Ein Executor, der sofort meldet, darf die Drehung nicht dauerhaft blockieren."""
    calls = []

    class SyncExecutor(FakeExecutor):
        def submit(self, ref, action, steps=0, pressed=True):
            calls.append(steps)
            self.on_result(ref, Result(True))

    e = make_engine(make_profile(), executor_factory=SyncExecutor)
    e.handle(RotateEvent(1, +1))
    e.handle(RotateEvent(1, +1))
    assert calls == [1, 1]


def test_submit_after_shutdown_is_logged_not_raised(caplog):
    attempts = []

    class Closed(FakeExecutor):
        def submit(self, ref, action, steps=0, pressed=True):
            attempts.append(steps)
            raise RuntimeError("cannot schedule new futures after shutdown")

    e = make_engine(make_profile(), executor_factory=Closed)
    with caplog.at_level("ERROR"):
        e.handle(RotateEvent(1, +1))
        e.handle(RotateEvent(1, +1))  # nicht als "laeuft noch" haengen geblieben
    assert "nicht eingereiht" in caplog.text
    assert attempts == [1, 1]


def test_real_executor_result_comes_back_through_post():
    import queue

    from neondeck.actions.base import ActionContext, Executor

    q = queue.Queue()
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[5] = Assignment({"type": "unsupported", "original": "X"})
    draws = []
    e = make_engine(p, lambda d, b: draws.append((d, b)),
                    executor_factory=lambda call, res: Executor(ActionContext(engine_call=call),
                                                                res), post=q.put)
    e.redraw_all()
    e.handle(TouchEvent(1, *TILE5, True))
    e.handle(TouchEvent(1, *TILE5, False))
    q.get(timeout=5)()  # im Test-Thread anwenden, nicht im Worker
    center = [b for d, b in draws if d is Display.CENTER][-1]
    assert tuple(pixels(Display.CENTER, center)[90 + 45, 90 + 1]) == RED
    e.shutdown()


def test_post_is_required():
    with pytest.raises(TypeError):
        EnginePorts(lambda d, b: None, lambda c: None, FakeExecutor)


def _profile_with_ws2_knob():
    p = make_profile()
    p.workspaces[1].encoders[0] = Encoder(rotate={"type": "brightness"})
    return p


def test_rotation_steps_do_not_move_to_other_workspace():
    rig = Rig(_profile_with_ws2_knob())
    rig.engine.handle(RotateEvent(1, +1))   # laeuft
    rig.engine.handle(RotateEvent(1, +1))   # gesammelt fuer ws1
    rig.engine.handle(ButtonEvent(8, True))  # -> ws2
    rig.ex.finish()
    assert [c[1] for c in rig.ex.calls] == [{"type": "volume"}]


def test_rotation_window_dropped_on_workspace_change():
    later = []
    rig = Rig(_profile_with_ws2_knob(), call_later=lambda d, fn: later.append(fn))
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.handle(ButtonEvent(8, True))
    for fn in later:
        fn()
    assert rig.ex.calls == []


def test_rotation_pending_dropped_on_set_profile():
    rig = Rig()
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.handle(RotateEvent(1, +1))
    rig.engine.set_profile(make_profile())
    rig.ex.finish()
    assert len(rig.ex.calls) == 1


def test_reset_input_releases_and_forgets_touches():
    p = make_profile()
    p.square[15] = Assignment({"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]})
    rig = Rig(p)
    rig.engine.redraw_all()
    rig.engine.handle(ButtonEvent(15, True))
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) == (0xF8, 0xFC, 0xF8)
    rig.engine.reset_input()
    assert rig.ex.calls[-1][0] == ControlRef("square", 0) and rig.ex.calls[-1][3] is False
    assert tuple(rig.last(Display.CENTER)[90 + 45, 90 + 1]) == (0, 0, 0)
    n = len(rig.ex.calls)
    rig.engine.handle(TouchEvent(1, *TILE5, False))   # altes "up" nach Wiederverbinden
    rig.engine.handle(ButtonEvent(15, False))
    assert len(rig.ex.calls) == n


def test_posted_call_errors_are_logged_not_raised(caplog):
    queued = []

    def bad_status(msg):
        raise RuntimeError("tray kaputt")

    rig = Rig(post=queued.append, on_status=bad_status)
    rig.tap(*TILE5)
    rig.ex.finish(result=Result(False, "x"))
    rig.ex.engine_call("open_config", {})
    with caplog.at_level("ERROR"):
        for fn in queued:
            fn()  # darf nicht werfen
    assert "tray kaputt" in caplog.text


# --- Einstellungsfenster: Ansicht behalten, Testen ------------------------------------

def test_set_profile_keep_view_keeps_workspace_and_page():
    p = make_profile()
    p.workspaces[1].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = Rig(p)
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("page", {"index": 1})
    rig.engine.set_profile(p, keep_view=True)
    assert (rig.engine.workspace_id, rig.engine.page_index) == ("ws2", 1)
    del p.workspaces[1].touch_pages[1]  # Seite entfernt: auf die letzte vorhandene
    rig.engine.set_profile(p, keep_view=True)
    assert (rig.engine.workspace_id, rig.engine.page_index) == ("ws2", 0)
    del p.workspaces[1]  # Arbeitsbereich entfernt: Heim-Arbeitsbereich
    rig.engine.set_profile(p, keep_view=True)
    assert (rig.engine.workspace_id, rig.engine.page_index) == ("ws1", 0)


def test_set_profile_keep_view_redraws_everything():
    rig = Rig()
    n = len(rig.draws)
    rig.engine.set_profile(rig.engine.profile, keep_view=True)
    assert {d for d, _ in rig.draws[n:]} == set(Display)


def test_trigger_runs_action_through_executor():
    rig = Rig()
    rig.engine.trigger(ControlRef("touch", 3), {"type": "run", "command": "kate"})
    assert rig.ex.calls == [(ControlRef("touch", 3), {"type": "run", "command": "kate"}, 0, True)]
    rig.engine.trigger(ControlRef("knob", 0), {"type": "volume"}, steps=1)
    assert rig.ex.calls[-1] == (ControlRef("knob", 0), {"type": "volume"}, 1, True)
    rig.ex.finish(0, Result(False, "kaputt"))
    assert rig.status[-1] == "Fehler: kaputt"


def test_trigger_hold_key_presses_and_releases():
    rig = Rig()
    action = {"type": "hold_key", "keys": "KEY_LEFTSHIFT"}
    rig.engine.trigger(ControlRef("square", 0), action)
    assert [c[3] for c in rig.ex.calls] == [True, False]


def test_trigger_navigation_and_live_types_run_directly():
    rig = Rig()
    rig.engine.trigger(ControlRef("round", 1), {"type": "workspace", "id": "ws2"})
    assert rig.engine.workspace_id == "ws2"
    rig.engine.trigger(ControlRef("touch", 0), {"type": "clock"})
    rig.engine.trigger(ControlRef("touch", 0), {})
    assert rig.ex.calls == []


def test_encoder_label():
    from neondeck.engine.painter import encoder_label
    assert encoder_label(Encoder(label="Zoom", rotate={"type": "volume"})) == "Zoom"
    assert encoder_label(Encoder(rotate={"type": "volume"})) == "Lautstärke"
    assert encoder_label(Encoder(press={"type": "mute_toggle"})) == "Stummschalten"
    assert encoder_label(Encoder()) == ""


def test_set_profile_keep_view_keeps_live_state():
    """Bearbeiten im Fenster darf laufende Stoppuhr, Leistenwert, Blinken und gesammelte
    Drehungen nicht verlieren."""
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[0] = Assignment({"type": "stopwatch"})
    rig = Rig(p, call_later=lambda delay, fn: None)
    rig.tap(105, 45)                                   # Stoppuhr starten
    rig.clock.t += 5
    rig.engine.handle(RotateEvent(1, 1))               # Regler 0: Lautstaerke einreihen
    rig.engine.dispatch.spinner.flush(ControlRef("knob", 0))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))         # Wert in der Leiste
    rig.engine.handle(RotateEvent(1, 3))               # gesammelt, noch nicht ausgefuehrt
    rig.engine.trigger(ControlRef("touch", 5), {"type": "run", "command": "x"})
    rig.ex.finish(result=Result(False, "kaputt"))      # Kachel 5 blinkt rot
    watch = rig.engine.controls.stopwatch(0)
    rig.engine.set_profile(p, keep_view=True)
    assert rig.engine.controls.stopwatch(0) is watch and watch.running
    assert watch.elapsed(rig.clock.t) == pytest.approx(5)
    assert rig.engine.state.feedback.values[0][0] == "42 %"
    assert ControlRef("touch", 5) in rig.engine.state.feedback.flashes
    rig.engine.dispatch.spinner.flush(ControlRef("knob", 0))
    assert rig.ex.calls[-1][2] == 3                    # Drehungen nicht verworfen


def test_set_profile_keep_view_keeps_icon_cache():
    loads = []
    p = make_profile()
    p.workspaces[0].touch_pages[0].buttons[1] = Assignment(
        {"type": "run", "command": "x"}, ButtonImage(icon="svg:a.svg"))
    rig = Rig(p, icon_loader=lambda ref, size: loads.append(ref))
    rig.engine.redraw_all()
    rig.engine.set_profile(p, keep_view=True)
    assert loads == ["svg:a.svg"]


# --- Hooks und Laufzeit-Ueberschreibungen (API, Task P3) -------------------------------

def _solid_icon(color):
    from PIL import Image
    return lambda ref, size: Image.new("RGBA", (size, size), color + (255,))


def test_image_override_drawn_until_cleared_and_reloaded():
    loads = []
    colors = {"file:/a.png": (0, 0, 255)}

    def loader(ref, size):
        loads.append(ref)
        return _solid_icon(colors[ref])(ref, size) if ref in colors else None

    rig = Rig(icon_loader=loader)
    rig.engine.redraw_all()
    center = (90 + 45, 90 + 45)  # Mitte von Feld 5 (Zeile 1, Spalte 1)
    empty = (45, 45)              # Feld 0 ist unbelegt
    before = tuple(rig.last(Display.CENTER)[center])  # Text „Firefox“
    assert before != (0, 0, 0xF8)
    rig.engine.set_image_override(ControlRef("touch", 5), "/a.png")
    rig.engine.set_image_override(ControlRef("touch", 0), "/a.png")
    px = rig.last(Display.CENTER)
    assert tuple(px[center]) == (0, 0, 0xF8) and tuple(px[empty]) == (0, 0, 0xF8)
    # gleiche Datei, neuer Inhalt: wird neu geladen statt aus dem Zwischenspeicher
    colors["file:/a.png"] = (0, 255, 0)
    rig.engine.set_image_override(ControlRef("touch", 5), "/a.png")
    assert tuple(rig.last(Display.CENTER)[center]) == (0, 0xFC, 0)
    # bleibt ueber Seitenwechsel und Profil-Uebernahme bestehen
    rig.engine.set_profile(make_profile(), keep_view=True)
    rig.engine.set_profile(make_profile())
    assert tuple(rig.last(Display.CENTER)[center]) == (0, 0xFC, 0)
    rig.engine.set_image_override(ControlRef("touch", 5), None)
    rig.engine.set_image_override(ControlRef("touch", 0), None)
    px = rig.last(Display.CENTER)
    assert tuple(px[center]) == before and tuple(px[empty]) == (0, 0, 0)


def test_set_state_draws_state_image():
    p = make_profile()
    a = p.workspaces[0].touch_pages[0].buttons[5]
    from neondeck.profile.model import StateDef
    a.states = [StateDef(ButtonImage(bg="#ff0000")), StateDef(ButtonImage(bg="#00ff00"))]
    rig = Rig(p)
    rig.engine.redraw_all()
    center = (90 + 45, 90 + 2)
    assert tuple(rig.last(Display.CENTER)[center]) == (0, 0, 0)  # ohne Zustand: Grundbild
    rig.engine.set_state(ControlRef("touch", 5), 1)
    assert tuple(rig.last(Display.CENTER)[center]) == (0, 0xFC, 0)
    rig.engine.set_state(ControlRef("touch", 5), 0)
    assert tuple(rig.last(Display.CENTER)[center]) == (0xF8, 0, 0)
    rig.engine.set_state(ControlRef("touch", 5), 7)  # gibt es nicht: Grundbild
    assert tuple(rig.last(Display.CENTER)[center]) == (0, 0, 0)


def test_view_and_value_hooks():
    views, values = [], []
    p = make_profile()
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = Rig(p, on_view=lambda: views.append(rig.engine.view_state()),
              on_value=lambda ref, text: values.append((ref, text)))
    assert views == []  # der Aufbau meldet nichts
    rig.engine.call("page_next", {})
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.set_profile(make_profile())
    assert [(v["workspace"], v["page"]) for v in views] == [("ws1", 1), ("ws2", 0), ("ws1", 0)]
    assert views[0] == {"profile": "default", "workspace": "ws1", "page": 1, "page_count": 2,
                        "folder": None, "folder_stack": [],
                        "workspaces": [{"id": "ws1", "name": "Allgemein", "pages": 2},
                                       {"id": "ws2", "name": "Zwei", "pages": 1}]}
    rig.engine.handle(RotateEvent(1, 1))
    rig.ex.finish(result=Result(True, "42 %", value=42.0))
    assert values == [(ControlRef("knob", 0), "42 %")]


def test_action_for_each_control_kind():
    p = make_profile()
    a = p.workspaces[0].touch_pages[0].buttons[5]
    a.double, a.hold = {"type": "run", "command": "d"}, {"type": "run", "command": "h"}
    p.square[18] = Assignment({"type": "hotkey", "keys": ["KEY_B"]})  # Index 1 (oben rechts)
    p.workspaces[0].wheel.rotate = {"type": "volume"}
    p.workspaces[0].wheel.tap = {"type": "mute_toggle"}
    e = Rig(p).engine
    assert e.controls.action_for(ControlRef("touch", 5))["command"] == "firefox"
    assert e.controls.action_for(ControlRef("touch", 5), "double")["command"] == "d"
    assert e.controls.action_for(ControlRef("touch", 5), "hold")["command"] == "h"
    assert e.controls.action_for(ControlRef("touch", 0)) is None
    assert e.controls.action_for(ControlRef("round", 2)) == {"type": "hotkey", "keys": ["KEY_A"]}
    assert e.controls.action_for(ControlRef("square", 1)) == {"type": "hotkey", "keys": ["KEY_B"]}
    assert e.controls.action_for(ControlRef("knob", 0)) == {"type": "mute_toggle"}
    assert e.controls.action_for(ControlRef("strip", 0)) == {"type": "mute_toggle"}
    assert e.controls.action_for(ControlRef("knob", 0), "rotate") == {"type": "volume"}
    assert e.controls.action_for(ControlRef("wheel", 0), "rotate") == {"type": "volume"}
    assert e.controls.action_for(ControlRef("wheel", 0)) == {"type": "mute_toggle"}
    assert e.controls.action_for(ControlRef("touch", 5), "rotate") is None


def test_set_profile_rolls_back_when_drawing_fails():
    p = make_profile()
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = Rig(p)
    rig.engine.call("page_next", {})
    bad = make_profile()
    bad.workspaces[0].touch_pages[0].buttons[5].image.bg = "#zzzzzz"  # PIL kennt die Farbe nicht
    with pytest.raises(ValueError):
        rig.engine.set_profile(bad, keep_view=True)
    assert rig.engine.profile is p
    assert (rig.engine.workspace_id, rig.engine.page_index) == ("ws1", 1)
    with pytest.raises(ValueError):
        rig.engine.set_profile(bad)
    assert rig.engine.profile is p and rig.engine.page_index == 1
    rig.draws.clear()
    rig.engine.redraw_all()  # das alte Profil zeichnet weiter
    assert rig.count(Display.CENTER) == 1
