import subprocess

import pytest
from evdev import ecodes

from neondeck.actions import execute, key_actions, keyboard, registry
from neondeck.actions.base import ActionContext
from neondeck.actions.keyboard import Keyboard
from neondeck.core import proc
from neondeck.core.keymap import CHAR_MAP, LETTER_KEY
from support.fakes import FakeRun, make_ctx


class FakeUinput:
    """Collects key events as (name without KEY_, value); counts syn() calls."""

    def __init__(self):
        self.events = []
        self.syns = 0

    def write(self, type_, code, value):
        assert type_ == ecodes.EV_KEY
        name = ecodes.KEY[code]
        if isinstance(name, list):
            name = name[0]
        self.events.append((name.removeprefix("KEY_"), value))

    def syn(self):
        self.syns += 1


@pytest.fixture
def dev():
    return FakeUinput()


@pytest.fixture
def kb(dev):
    return Keyboard(dev, sleep=lambda s: None)


def test_registry_has_input_types():
    assert {"hotkey", "hold_key", "text", "adjust_hotkey"} <= registry().keys()
    assert registry()["adjust_hotkey"].kinds == {"rotate"}
    assert registry()["hotkey"].kinds == {"press"}


def test_tap_order(dev, kb):
    kb.tap("KEY_LEFTCTRL+KEY_T")
    assert dev.events == [("LEFTCTRL", 1), ("T", 1), ("T", 0), ("LEFTCTRL", 0)]
    assert dev.syns == 4


def test_tap_three_keys_releases_modifiers_in_reverse(dev, kb):
    kb.tap("KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_T")
    assert dev.events == [("LEFTCTRL", 1), ("LEFTSHIFT", 1), ("T", 1), ("T", 0),
                          ("LEFTSHIFT", 0), ("LEFTCTRL", 0)]


def test_tap_pauses_between_down_and_up(dev):
    pauses = []
    Keyboard(dev, sleep=pauses.append).tap("KEY_A")
    assert pauses == [0.008]


def test_tap_unknown_key_raises_without_events(dev, kb):
    with pytest.raises(ValueError, match="KEY_NIX"):
        kb.tap("KEY_LEFTCTRL+KEY_NIX")
    assert dev.events == []


def test_type_umlaut_and_at(dev, kb):
    kb.type_text("ä@Z")
    ev = dev.events
    assert ("APOSTROPHE", 1) in ev
    i = ev.index(("RIGHTALT", 1))
    assert ev[i + 1] == ("Q", 1)
    j = ev.index(("LEFTSHIFT", 1))
    assert ev[j + 1] == ("Y", 1)


def test_type_dead_circumflex_followed_by_space(dev, kb):
    kb.type_text("^")
    assert dev.events == [("GRAVE", 1), ("GRAVE", 0), ("SPACE", 1), ("SPACE", 0)]


def test_type_unknown_char(dev, kb):
    with pytest.raises(ValueError, match="ж"):
        kb.type_text("aж")
    assert dev.events == []  # validated before anything is typed


def test_char_map_german_layout():
    assert CHAR_MAP["y"] == ("KEY_Z", False, False)
    assert CHAR_MAP["z"] == ("KEY_Y", False, False)
    assert CHAR_MAP["Y"] == ("KEY_Z", True, False)
    assert CHAR_MAP["ß"] == ("KEY_MINUS", False, False)
    assert CHAR_MAP["?"] == ("KEY_MINUS", True, False)
    assert CHAR_MAP["€"] == ("KEY_E", False, True)
    assert CHAR_MAP["|"] == ("KEY_102ND", False, True)
    assert CHAR_MAP["}"] == ("KEY_0", False, True)
    assert CHAR_MAP["'"] == ("KEY_BACKSLASH", True, False)
    assert CHAR_MAP["°"] == ("KEY_GRAVE", True, False)
    assert CHAR_MAP["\n"] == ("KEY_ENTER", False, False)
    for code, _shift, _altgr in CHAR_MAP.values():
        assert code in ecodes.ecodes, code


def test_letter_key_is_derived_from_char_map():
    assert LETTER_KEY["y"] == "KEY_Z" and LETTER_KEY["z"] == "KEY_Y"
    assert LETTER_KEY["a"] == "KEY_A" and len(LETTER_KEY) == 26


def test_text_auto_without_wlcopy(monkeypatch, dev, kb):
    monkeypatch.setattr(key_actions.shutil, "which", lambda name: None)
    run = FakeRun()
    r = execute({"type": "text", "text": "ab"}, make_ctx(keyboard=kb, run=run))
    assert r.ok
    assert run.calls == []
    assert dev.events == [("A", 1), ("A", 0), ("B", 1), ("B", 0)]


def test_text_paste(monkeypatch, dev, kb):
    monkeypatch.setattr(key_actions.shutil, "which", lambda name: "/usr/bin/wl-copy")
    run = FakeRun()
    r = execute({"type": "text", "text": "Hallo"}, make_ctx(keyboard=kb, run=run))
    assert r.ok
    argv, kw = run.calls[0], run.options[0]
    assert argv == ["wl-copy", "--", "Hallo"]
    # wl-copy forks and keeps serving the clipboard: no captured pipes, bounded wait
    assert kw["stdout"] is subprocess.DEVNULL and kw["stderr"] is subprocess.DEVNULL
    assert kw["timeout"] > 0
    assert dev.events == [("LEFTCTRL", 1), ("V", 1), ("V", 0), ("LEFTCTRL", 0)]


def test_text_mode_type_ignores_wlcopy(monkeypatch, dev, kb):
    monkeypatch.setattr(key_actions.shutil, "which", lambda name: "/usr/bin/wl-copy")
    run = FakeRun()
    r = execute({"type": "text", "text": "x", "mode": "type"}, make_ctx(keyboard=kb, run=run))
    assert r.ok and run.calls == []
    assert dev.events == [("X", 1), ("X", 0)]


def test_text_paste_wlcopy_fails(monkeypatch, dev, kb):
    r = execute({"type": "text", "text": "x", "mode": "paste"}, make_ctx(keyboard=kb, run=FakeRun({"wl-copy": (1, "")})))
    assert not r.ok and "wl-copy" in r.message
    assert dev.events == []


def test_text_unknown_char_reports_error(monkeypatch, dev, kb):
    r = execute({"type": "text", "text": "ж", "mode": "type"}, make_ctx(keyboard=kb))
    assert not r.ok and "ж" in r.message


def test_hotkey_taps_on_press_only(dev, kb):
    ctx = make_ctx(keyboard=kb)
    assert execute({"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_A"}, ctx).ok
    assert execute({"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_A"}, ctx, pressed=False).ok
    assert dev.events == [("LEFTCTRL", 1), ("A", 1), ("A", 0), ("LEFTCTRL", 0)]


def test_hotkey_without_keys_fails(kb):
    r = execute({"type": "hotkey"}, make_ctx(keyboard=kb))
    assert not r.ok


def test_adjust_hotkey_steps(dev, kb):
    a = {"type": "adjust_hotkey", "left": "KEY_LEFT", "right": "KEY_RIGHT"}
    assert execute(a, make_ctx(keyboard=kb), steps=-3).ok
    assert dev.events == [("LEFT", 1), ("LEFT", 0)] * 3
    dev.events.clear()
    assert execute(a, make_ctx(keyboard=kb), steps=2).ok
    assert dev.events == [("RIGHT", 1), ("RIGHT", 0)] * 2


def test_hold_key_press_release(dev, kb):
    a = {"type": "hold_key", "keys": "KEY_LEFTSHIFT+KEY_A"}
    assert execute(a, make_ctx(keyboard=kb), pressed=True).ok
    assert dev.events == [("LEFTSHIFT", 1), ("A", 1)]
    dev.events.clear()
    assert execute(a, make_ctx(keyboard=kb), pressed=False).ok
    assert dev.events == [("A", 0), ("LEFTSHIFT", 0)]


def test_keyboard_creates_uinput_lazily(monkeypatch):
    created = []

    class FakeUInput(FakeUinput):
        def __init__(self, events, name):
            super().__init__()
            created.append((events, name))

    monkeypatch.setattr(keyboard, "UInput", FakeUInput)
    kb = Keyboard(sleep=lambda s: None)
    assert created == []
    kb.tap("KEY_A")
    kb.tap("KEY_B")
    assert len(created) == 1
    events, name = created[0]
    assert name == "Neondeck CT Tastatur"
    codes = events[ecodes.EV_KEY]
    assert ecodes.KEY_A in codes and ecodes.KEY_102ND in codes
    assert ecodes.BTN_LEFT not in codes


def test_default_run_drops_capture_when_pipes_given(monkeypatch):
    seen = {}
    monkeypatch.setattr(proc.subprocess, "run", lambda argv, **kw: seen.update(kw))
    ActionContext(engine_call=lambda n, a: None).run(["x"], stdout=subprocess.DEVNULL,
                                                      stderr=subprocess.DEVNULL, timeout=2)
    assert "capture_output" not in seen and seen["timeout"] == 2
    seen.clear()
    ActionContext(engine_call=lambda n, a: None).run(["x"])
    assert seen["capture_output"] is True and seen["timeout"] == 10
