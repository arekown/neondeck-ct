"""Engine-Pruefstand: ``Engine`` mit Fake-Uhr, Fake-Executor und mitgeschriebenen Zeichnungen,
dazu das Standard-Testprofil und Helfer fuer Tasten und Touch."""
from __future__ import annotations

from dataclasses import fields

import numpy as np

from neondeck.device.protocol import ButtonEvent, TouchEvent
from neondeck.engine import Engine
from neondeck.engine.ports import EngineHooks, EngineOptions, EnginePorts
from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    Profile,
    TouchPage,
    Workspace,
)

from .fakes import T0, Clock, FakeExecutor, Timers

__all__ = ["T0", "TILE5", "NullExecutor", "Rig", "finger_down", "finger_up", "make_engine",
           "make_profile", "make_rig", "pixels", "press", "profile_with", "release"]

TILE5 = (60 + 90 + 45, 90 + 45)  # Touch-Koordinaten der Mitte von Feld 5


class NullExecutor:
    """Executor, der nichts ausfuehrt (Engine nur fuer Ansicht/Editor)."""

    def __init__(self, *_):
        pass

    def submit(self, *a, **k):
        pass

    def shutdown(self):
        pass


def _split(kw):
    """Schluesselwoerter auf ``EnginePorts``, ``EngineHooks`` und ``EngineOptions`` verteilen."""
    parts = {}
    for cls in (EnginePorts, EngineHooks, EngineOptions):
        names = {f.name for f in fields(cls)}
        parts[cls] = {k: kw.pop(k) for k in list(kw) if k in names}
    assert not kw, f"unbekannte Engine-Parameter: {sorted(kw)}"
    return parts[EnginePorts], parts[EngineHooks], parts[EngineOptions]


def make_engine(profile, draw=lambda d, b: None, leds=lambda c: None,
                executor_factory=NullExecutor, icon_loader=lambda ref, size: None, **kw):
    """Engine wie im Dienst, aber mit Fakes; ``kw`` sind Felder von ``EnginePorts``,
    ``EngineHooks`` oder ``EngineOptions`` (``post`` ruft sofort auf)."""
    ports, hooks, options = _split({"post": lambda fn: fn(), **kw})
    return Engine(profile, EnginePorts(draw, leds, executor_factory, icon_loader, **ports),
                  hooks=EngineHooks(**hooks), options=EngineOptions(**options))


class Rig:
    def __init__(self, profile=None, call_later=None, post=None, icon_loader=None, clock=None,
                 **kw):
        self.draws = []
        self.leds = []
        self.clock = clock or Clock()
        self.ex = None
        self.status = []
        self.opened = []

        def factory(engine_call, on_result):
            self.ex = FakeExecutor(engine_call, on_result)
            return self.ex

        opts = dict(clock=self.clock, call_later=call_later,
                    on_open_config=lambda: self.opened.append(True),
                    on_status=self.status.append, post=post or (lambda fn: fn()))
        opts.update(kw)
        self.engine = make_engine(profile or make_profile(),
                                  lambda d, b: self.draws.append((d, b)), self.leds.append,
                                  factory, icon_loader or (lambda ref, size: None), **opts)

    def last(self, display):
        for d, b in reversed(self.draws):
            if d is display:
                return pixels(d, b)
        raise AssertionError(f"{display} nie gezeichnet")

    def count(self, display):
        return sum(1 for d, _ in self.draws if d is display)

    def tap(self, x, y, finger=1, x_up=None):
        self.engine.handle(TouchEvent(finger, x, y, True))
        self.engine.handle(TouchEvent(finger, x if x_up is None else x_up, y, False))


def pixels(display, data):
    """RGB565-Bytes -> (h, w, 3) uint8 (obere Bits)."""
    v = np.frombuffer(data, dtype=">u2" if display.big_endian else "<u2").reshape(
        display.height, display.width).astype(np.uint16)
    r = (v >> 8) & 0xF8
    g = (v >> 3) & 0xFC
    b = (v << 3) & 0xF8
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def make_profile():
    p = Profile.empty()
    ws1 = p.workspaces[0]
    ws1.touch_pages[0].buttons[5] = Assignment({"type": "run", "command": "firefox"},
                                               ButtonImage(text="Firefox"))
    ws1.encoders[0] = Encoder(rotate={"type": "volume"}, press={"type": "mute_toggle"},
                              label="Lautstärke")
    ws1.encoders[1] = Encoder(rotate={"type": "brightness"}, press={"type": "brightness_reset"})
    ws1.wheel.display = "blank"
    ws2 = Workspace("ws2", "Zwei", [TouchPage("p1", "Seite 1")])
    ws2.wheel.display = "label"
    ws2.wheel.label = "ZWEI"
    p.workspaces.append(ws2)
    p.round[7] = Assignment({"type": "workspace", "id": "ws1"})
    p.round[8] = Assignment({"type": "workspace", "id": "ws2"})
    p.round[9] = Assignment({"type": "hotkey", "keys": ["KEY_A"]})
    return p


# --- Tasten-Logik mit Fake-Timern ----------------------------------------------------------

def make_rig(profile, **kw):
    holder = {}

    def call_later(delay, fn):
        holder["timers"](delay, fn)

    clock = Clock()  # Haltedauer/Doppeltipp-Fenster laufen auf der Fake-Uhr
    rig = Rig(profile, call_later=call_later, clock=clock, monotonic=clock, **kw)
    rig.timers = holder["timers"] = Timers(rig.clock)
    return rig


def profile_with(square=None, tile=None):
    p = make_profile()
    if square is not None:
        p.square[15] = square
    if tile is not None:
        p.workspaces[0].touch_pages[0].buttons[5] = tile
    return p


def press(rig, code=15):
    rig.engine.handle(ButtonEvent(code, True))


def release(rig, code=15):
    rig.engine.handle(ButtonEvent(code, False))


def finger_down(rig, x=TILE5[0], y=TILE5[1], finger=1):
    rig.engine.handle(TouchEvent(finger, x, y, True))


def finger_up(rig, x=TILE5[0], y=TILE5[1], finger=1):
    rig.engine.handle(TouchEvent(finger, x, y, False))
