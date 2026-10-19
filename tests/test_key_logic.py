"""Tasten-Logik: Tippen, Doppeltippen, Halten (Fake-Uhr, keine echten Wartezeiten)."""
from neondeck.core.settings import Settings
from neondeck.device.layout import ControlRef
from neondeck.device.protocol import ButtonEvent, TouchEvent
from neondeck.profile.model import Assignment, TouchPage
from support.engine_rig import (
    TILE5,
    Rig,
    finger_down,
    finger_up,
    make_profile,
    make_rig,
    press,
    profile_with,
    release,
)
from support.fakes import Clock

A = {"type": "run", "command": "tippen"}
D = {"type": "run", "command": "doppelt"}
H = {"type": "run", "command": "halten"}
SQ0 = ControlRef("square", 0)
T5 = ControlRef("touch", 5)


def fired(rig):
    return [(ref, action.get("command") or action.get("type"), pressed)
            for ref, action, _steps, pressed in rig.ex.calls]


# --- Ohne Doppeltippen/Halten: sofort --------------------------------------------------

def test_tap_without_double_hold_immediate():
    rig = make_rig(profile_with(square=Assignment(A), tile=Assignment(A)))
    press(rig)
    assert fired(rig) == [(SQ0, "tippen", True)]  # beim Druecken, ohne Wartezeit
    release(rig)
    rig.tap(*TILE5)
    assert fired(rig)[-1] == (T5, "tippen", True)
    assert rig.timers.pending == []  # nichts eingeplant: keine zusaetzliche Verzoegerung


def test_hold_key_without_double_hold_keeps_press_release():
    rig = make_rig(profile_with(square=Assignment({"type": "hold_key", "keys": ["KEY_A"]})))
    press(rig)
    rig.timers.advance(2.0)
    release(rig)
    assert fired(rig) == [(SQ0, "hold_key", True), (SQ0, "hold_key", False)]


def test_knob_press_stays_immediate():
    rig = make_rig(make_profile())
    rig.engine.handle(ButtonEvent(1, True))
    assert fired(rig) == [(ControlRef("knob", 0), "mute_toggle", True)]


# --- Doppeltippen -------------------------------------------------------------------------

def test_double_tap():
    rig = make_rig(profile_with(square=Assignment(A, double=D)))
    press(rig)
    release(rig)
    rig.timers.advance(0.1)
    assert fired(rig) == []
    press(rig)  # zweites Druecken im Fenster: sofort Doppeltippen
    assert fired(rig) == [(SQ0, "doppelt", True)]
    release(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == [(SQ0, "doppelt", True)]  # das einfache Tippen kommt nie


def test_double_tap_on_touch_fires_on_second_lift():
    rig = make_rig(profile_with(tile=Assignment(A, double=D)))
    rig.tap(*TILE5)
    rig.timers.advance(0.1)
    finger_down(rig)
    assert fired(rig) == []
    finger_up(rig)
    assert fired(rig) == [(T5, "doppelt", True)]
    rig.timers.advance(1.0)
    assert fired(rig) == [(T5, "doppelt", True)]


def test_double_tap_after_window_is_two_taps():
    rig = make_rig(profile_with(square=Assignment(A, double=D)))
    press(rig)
    release(rig)
    rig.timers.advance(0.31)
    press(rig)
    release(rig)
    rig.timers.advance(0.31)
    assert fired(rig) == [(SQ0, "tippen", True), (SQ0, "tippen", True)]


def test_double_tap_hold_key_held_until_second_release():
    rig = make_rig(profile_with(square=Assignment(A, double={"type": "hold_key",
                                                             "keys": ["KEY_B"]})))
    press(rig)
    release(rig)
    press(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == [(SQ0, "hold_key", True)]
    release(rig)
    assert fired(rig) == [(SQ0, "hold_key", True), (SQ0, "hold_key", False)]


# --- Halten ----------------------------------------------------------------------------------

def test_hold():
    rig = make_rig(profile_with(square=Assignment(A, hold=H), tile=Assignment(A, hold=H)))
    press(rig)
    rig.timers.advance(0.49)
    assert fired(rig) == []
    rig.timers.advance(0.01)  # Schwelle erreicht, Taste noch gedrueckt
    assert fired(rig) == [(SQ0, "halten", True)]
    release(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == [(SQ0, "halten", True)]  # kein Tippen danach
    # Touch: Finger bleibt liegen
    finger_down(rig)
    rig.timers.advance(0.5)
    assert fired(rig)[-1] == (T5, "halten", True)
    finger_up(rig)
    rig.timers.advance(1.0)
    assert fired(rig)[-1] == (T5, "halten", True) and len(fired(rig)) == 2


def test_hold_key_as_hold_action_released_with_button():
    rig = make_rig(profile_with(square=Assignment(A, hold={"type": "hold_key",
                                                           "keys": ["KEY_LEFTSHIFT"]})))
    press(rig)
    rig.timers.advance(0.6)
    assert fired(rig) == [(SQ0, "hold_key", True)]
    release(rig)
    assert fired(rig) == [(SQ0, "hold_key", True), (SQ0, "hold_key", False)]


def test_short_press_with_hold_only_taps_on_release():
    rig = make_rig(profile_with(square=Assignment(A, hold=H)))
    press(rig)
    rig.timers.advance(0.2)
    release(rig)
    assert fired(rig) == [(SQ0, "tippen", True)]  # ohne Doppeltippen: sofort beim Loslassen
    rig.timers.advance(1.0)
    assert fired(rig) == [(SQ0, "tippen", True)]


def test_touch_swipe_wins_over_hold():
    p = profile_with(tile=Assignment(A, hold=H, double=D))
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = make_rig(p)
    finger_down(rig)
    rig.timers.advance(0.2)
    rig.engine.handle(TouchEvent(1, TILE5[0] - 150, TILE5[1], True))  # zieht weg
    rig.timers.advance(0.5)
    finger_up(rig, x=TILE5[0] - 150)
    rig.timers.advance(1.0)
    assert fired(rig) == [] and rig.engine.page_index == 1


def test_custom_thresholds_from_settings():
    s = Settings(double_ms=200, hold_ms=800)
    rig = make_rig(profile_with(square=Assignment(A, double=D, hold=H)),
                   double_ms=s.double_ms, hold_ms=s.hold_ms)
    press(rig)
    rig.timers.advance(0.7)
    assert fired(rig) == []
    rig.timers.advance(0.1)
    assert fired(rig) == [(SQ0, "halten", True)]
    release(rig)
    press(rig)
    release(rig)
    rig.timers.advance(0.2)
    assert fired(rig)[-1] == (SQ0, "tippen", True)


def test_tap_waits_double_window():
    rig = make_rig(profile_with(square=Assignment(A, double=D),
                                tile=Assignment(A, double=D)))
    press(rig)
    release(rig)
    rig.timers.advance(0.29)
    assert fired(rig) == []
    rig.timers.advance(0.01)  # Fenster (300 ms) abgelaufen: einfaches Tippen
    assert fired(rig) == [(SQ0, "tippen", True)]
    rig.tap(*TILE5)
    rig.timers.advance(0.29)
    assert fired(rig) == [(SQ0, "tippen", True)]
    rig.timers.advance(0.01)
    assert fired(rig)[-1] == (T5, "tippen", True)


def test_lock_drops_pending_tap_and_hold():
    rig = make_rig(profile_with(square=Assignment(A, double=D, hold=H)))
    press(rig)
    release(rig)
    rig.engine.lock()
    rig.timers.advance(1.0)
    rig.engine.unlock()
    press(rig)
    rig.engine.reset_input()  # Geraet getrennt, waehrend die Taste gedrueckt ist
    rig.timers.advance(1.0)
    assert fired(rig) == []


def test_without_call_later_hold_by_duration_tap_immediate():
    clock = Clock()
    rig = Rig(profile_with(square=Assignment(A, double=D, hold=H)), clock=clock, monotonic=clock)
    press(rig)
    rig.clock.t += 0.6
    release(rig)
    press(rig)
    release(rig)
    assert fired(rig) == [(SQ0, "halten", True), (SQ0, "tippen", True)]


def test_api_style_activate_runs_double_and_hold():
    rig = make_rig(profile_with(square=Assignment(A, double=D, hold=H)))
    assert rig.engine.activate(SQ0, "double") and rig.engine.activate(SQ0, "hold")
    assert rig.engine.activate(SQ0, "tap")
    assert fired(rig) == [(SQ0, "doppelt", True), (SQ0, "halten", True), (SQ0, "tippen", True)]
    assert not rig.engine.activate(ControlRef("square", 5), "double")


def test_thresholds_loaded_and_validated(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    path = tmp_path / "config" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"double_ms": 250, "hold_ms": 700}))
    s = Settings.load()
    assert (s.double_ms, s.hold_ms) == (250, 700)
    for bad in ({"double_ms": 5, "hold_ms": 99999}, {"double_ms": True, "hold_ms": "600"}):
        path.write_text(json.dumps(bad))
        s = Settings.load()
        assert (s.double_ms, s.hold_ms) == (300, 500)


# --- Ansichtswechsel verwirft Gesten (Review-Runde 1) ----------------------------------------

P2 = {"type": "run", "command": "seite2"}


def two_page_profile(tile1, tile2):
    p = profile_with(tile=tile1)
    page2 = TouchPage("p2", "Seite 2")
    page2.buttons[5] = tile2
    p.workspaces[0].touch_pages.append(page2)
    return p


def test_page_change_drops_pending_double_tap():
    rig = make_rig(two_page_profile(Assignment(A, double=D), Assignment(P2)))
    rig.tap(*TILE5)
    rig.engine.call("page_next", {})
    rig.tap(*TILE5)  # Feld 5 auf Seite 2: eigene Aktion, kein Doppeltippen der alten Seite
    rig.timers.advance(1.0)
    assert fired(rig) == [(T5, "seite2", True)]


def test_page_change_new_gesture_on_same_slot():
    rig = make_rig(two_page_profile(Assignment(A, double=D), Assignment(P2, double=D)))
    rig.tap(*TILE5)
    rig.engine.call("page_next", {})
    rig.tap(*TILE5)
    rig.timers.advance(1.0)
    assert fired(rig) == [(T5, "seite2", True)]


def test_page_change_drops_pending_hold():
    rig = make_rig(two_page_profile(Assignment(A, hold=H), Assignment(P2)))
    finger_down(rig)
    rig.engine.call("page_next", {})  # z. B. per API/CLI
    rig.timers.advance(1.0)
    finger_up(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == []


def test_workspace_change_drops_pending_tap():
    rig = make_rig(profile_with(square=Assignment(A, double=D, hold=H)))
    press(rig)
    release(rig)
    rig.engine.call("workspace", {"id": "ws2"})
    rig.timers.advance(1.0)
    press(rig)
    rig.engine.call("workspace", {"id": "ws1"})
    rig.timers.advance(1.0)
    release(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == []


def test_profile_change_drops_pending_hold_and_tap():
    rig = make_rig(profile_with(square=Assignment(A, hold=H)))
    press(rig)
    rig.engine.set_profile(profile_with(square=Assignment(P2)))  # Dynamic Mode / Editor
    rig.timers.advance(1.0)
    release(rig)
    assert fired(rig) == []
    press(rig)  # neue Belegung: sofort
    assert fired(rig) == [(SQ0, "seite2", True)]


def test_dynamic_profile_switch_drops_pending_double_window():
    rig = make_rig(profile_with(square=Assignment(A, double=D)))
    press(rig)
    release(rig)
    other = profile_with(square=Assignment(P2, double=D))
    other.id = "anderes"
    rig.engine.set_profile(other)
    press(rig)  # nicht das zweite Tippen der alten Belegung
    release(rig)
    rig.timers.advance(1.0)
    assert fired(rig) == [(SQ0, "seite2", True)]


def test_held_hold_key_released_after_view_change():
    hk = {"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]}
    rig = make_rig(two_page_profile(Assignment(A, hold=hk), Assignment(P2)))
    rig.engine.profile.square[15] = Assignment(A, hold=hk)
    press(rig)
    finger_down(rig)
    rig.timers.advance(0.6)
    assert fired(rig) == [(SQ0, "hold_key", True), (T5, "hold_key", True)]
    rig.engine.call("page_next", {})
    rig.engine.call("workspace", {"id": "ws2"})
    release(rig)
    finger_up(rig)
    assert fired(rig)[2:] == [(SQ0, "hold_key", False), (T5, "hold_key", False)]


# --- Touch-Feinheiten (Review-Runde 1) ---------------------------------------------------------

def test_touch_tap_then_swipe_in_window_keeps_first_tap():
    p = profile_with(tile=Assignment(A, double=D))
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    rig = make_rig(p)
    rig.tap(*TILE5)
    finger_down(rig)  # zweites Beruehren im Fenster ...
    finger_up(rig, x=TILE5[0] - 150)  # ... wird zum Wischen
    rig.timers.advance(1.0)
    assert fired(rig) == [(T5, "tippen", True)] and rig.engine.page_index == 1


def test_touch_move_cancels_hold():
    rig = make_rig(profile_with(tile=Assignment(A, hold=H)))
    finger_down(rig)
    rig.timers.advance(0.2)
    rig.engine.handle(TouchEvent(1, TILE5[0] + 30, TILE5[1], True))  # noch auf Feld 5
    rig.timers.advance(0.5)
    assert fired(rig) == []  # bewegt: kein Halten (Wischen gewinnt)
    finger_up(rig, x=TILE5[0] + 30)
    assert fired(rig) == [(T5, "tippen", True)]


def test_ignored_second_finger_keeps_highlight():
    rig = make_rig(profile_with(tile=Assignment(A, hold=H)))
    finger_down(rig, finger=1)
    finger_down(rig, finger=2)
    finger_up(rig, finger=2)
    assert 5 in rig.engine.state.feedback.highlight
    finger_up(rig, finger=1)
    assert 5 not in rig.engine.state.feedback.highlight
    assert fired(rig) == [(T5, "tippen", True)]
