"""Eigene Tipp-Aktion je Leistenabschnitt (``Encoder.tap``): Engine, Profil, Editor."""
from neondeck.actions.base import Result
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import TouchEvent
from neondeck.profile.model import Encoder, Profile, validate_profile_json
from neondeck.profile.walk import iter_workspace_actions
from neondeck.render.draw import mix as _mix
from neondeck.render.palette import C_BG, C_MAGENTA
from support.engine_rig import Rig, make_profile
from support.window import choose_type, click

LOOP = {"type": "hotkey", "keys": ["KEY_L"]}
HOLD = {"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]}


def _rig(tap=LOOP, index=1, **kw):
    p = make_profile()
    p.workspaces[0].encoders[index].tap = tap
    return Rig(p, **kw)


def _touch(rig, section, down, finger=1):
    x = 30 if section < 3 else 450
    rig.engine.handle(TouchEvent(finger, x, (section % 3) * 90 + 45, down))


def test_strip_tap_runs_own_action_instead_of_knob_press():
    rig = _rig()
    _touch(rig, 1, True)
    _touch(rig, 1, False)
    assert [(ref, action) for ref, action, _, _ in rig.ex.calls] == [
        (ControlRef("strip", 1), LOOP)]
    _touch(rig, 0, True)                                    # ohne ``tap``: wie Regler-Druck
    _touch(rig, 0, False)
    assert rig.ex.calls[-1][:2] == (ControlRef("knob", 0), {"type": "mute_toggle"})


def test_strip_tap_holds_until_finger_lifts():
    rig = _rig(HOLD)
    _touch(rig, 1, True)
    assert [c[3] for c in rig.ex.calls] == [True]
    _touch(rig, 1, False)
    assert [c[3] for c in rig.ex.calls] == [True, False]   # losgelassen


def test_strip_tap_via_api_and_errors_flash_the_section():
    rig = _rig()
    e = rig.engine
    assert e.controls.action_for(ControlRef("strip", 1)) == LOOP
    assert e.controls.action_for(ControlRef("strip", 1), "hold") is None
    assert e.controls.action_for(ControlRef("strip", 0)) == {"type": "mute_toggle"}
    assert e.activate(ControlRef("strip", 1))
    assert rig.ex.calls[-1][:2] == (ControlRef("strip", 1), LOOP)
    rig.ex.finish(0, Result(False, "kaputt"))
    assert ControlRef("knob", 1) in e.state.feedback.flashes


def test_strip_touch_lights_section_magenta_in_cockpit():
    rig = _rig(device_look="cockpit")
    rig.engine.look_frame()
    _touch(rig, 1, True)
    img = rig.last(Display.LEFT)
    want = _mix(C_BG, C_MAGENTA, 0.3)
    assert all(abs(int(a) - int(b)) <= 8 for a, b in zip(img[90 + 20, 20], want))
    _touch(rig, 1, False)
    img = rig.last(Display.LEFT)
    assert not all(abs(int(a) - int(b)) <= 8 for a, b in zip(img[90 + 20, 20], want))


def test_profile_tap_roundtrip_and_validation():
    enc = Encoder.from_json({"press": {"type": "mute_toggle"}})
    assert enc.tap is None                                   # alte Profile
    enc.tap = LOOP
    assert Encoder.from_json(enc.to_json()).tap == LOOP
    p = Profile.empty()
    p.workspaces[0].encoders[2].tap = LOOP
    assert LOOP in list(iter_workspace_actions(p.workspaces[0]))
    d = p.to_json()
    assert validate_profile_json(d) == []
    d["workspaces"][0]["encoders"][2]["tap"] = "loop"
    assert any("tap" in err for err in validate_profile_json(d))


def test_editor_saves_strip_tap(window_rig):
    click(window_rig, ControlRef("knob", 2))
    choose_type(window_rig.win.editor.content.tap_form, "media")
    window_rig.win.flush()
    enc = window_rig.store.load("default").workspaces[0].encoders[2]
    assert enc.tap == {"type": "media", "key": "play_pause"}
