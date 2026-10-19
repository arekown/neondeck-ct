"""Leistenanzeige „system“: Messwerte (CPU/RAM, GPU im Hintergrund), Bild, Engine, Profil,
Editor."""
import subprocess
import threading

import numpy as np
import pytest

from neondeck.core.sysload import GpuSampler, SystemLoad, parse_gpu
from neondeck.device.layout import ControlRef, Display
from neondeck.engine.painter import strip_image
from neondeck.profile.model import (
    STRIP_KNOBS,
    STRIP_SYSTEM,
    Profile,
    Workspace,
    validate_profile_json,
)
from neondeck.render import look as looks
from neondeck.render import system_strip
from neondeck.render.images import to_rgb565
from neondeck.render.palette import ERROR_HEX
from support.engine_rig import Rig, make_profile, pixels
from support.fakes import Clock
from support.waiting import wait_until


class FakeLoad:
    """``SystemLoad``-Ersatz: feste Werte, merkt sich an/aus."""

    def __init__(self, values=(12, 34, 56, 78)):
        self.v = tuple(values)
        self.active = False
        self.switches = []

    def set_active(self, on):
        if on != self.active:
            self.switches.append(on)
        self.active = on

    def values(self):
        return self.v

    def close(self):
        self.set_active(False)


def _system_rig(side="right", **kw):
    p = make_profile()
    setattr(p.workspaces[0], f"strip_{side}", STRIP_SYSTEM)
    load = FakeLoad()
    rig = Rig(p, system_load=load, **kw)
    return rig, load


# --- Messwerte -----------------------------------------------------------------------------

def test_parse_gpu_output():
    assert parse_gpu("0, 37\n1, 2\n") == (37, 2)
    assert parse_gpu("0, 100\n") == (100, None)                 # nur eine GPU
    assert parse_gpu("0, [N/A]\nkaputt\n1, 140\n") == (None, 100)
    assert parse_gpu("") == (None, None)


def test_gpu_sampler_in_background_and_without_nvidia_smi():
    ran = threading.Event()

    def run():
        ran.set()
        return "0, 40\n1, 7\n"

    s = GpuSampler(run=run, every=0.01, available=lambda: True)
    s.set_active(True)
    assert wait_until(lambda: s.values == (40, 7))
    assert s.running
    s.set_active(False)
    assert wait_until(lambda: not s.running)
    missing = GpuSampler(run=run, available=lambda: False)
    missing.set_active(True)
    assert not missing.running and missing.values == (None, None)

    def fail():
        raise subprocess.TimeoutExpired("nvidia-smi", 5)

    broken = GpuSampler(run=fail, available=lambda: True)
    broken.values = (1, 2)
    broken.sample()
    assert broken.values == (None, None)


def test_system_load_reads_cpu_once_per_second():
    class Cpu:
        def __init__(self):
            self.samples, self.cpu, self.mem = 0, 0.25, 0.5

        def update(self):
            self.samples += 1

    class Gpu:
        values = (3, None)

        def set_active(self, on):
            self.on = on

    mono = Clock(0.0)
    cpu, gpu = Cpu(), Gpu()
    load = SystemLoad(cpu, gpu, monotonic=mono)
    assert load.values() == (None, 50, 3, None)                 # CPU erst nach zwei Lesungen
    assert cpu.samples == 1 and load.values() and cpu.samples == 1
    mono.t += 1.0
    assert load.values() == (25, 50, 3, None) and cpu.samples == 2
    load.set_active(True)
    assert gpu.on is True
    load.close()
    assert gpu.on is False


# --- Bild ----------------------------------------------------------------------------------

@pytest.mark.parametrize("draw", [system_strip.classic, system_strip.cockpit])
def test_system_strip_text_stays_out_of_the_stegs(draw, monkeypatch):
    """Schrift nur in Abschnitt 0 (oben) und 2 (unten); die Balken duerfen ueber die Stege."""
    values = (100, 88, None, 5)
    with_text = np.asarray(draw(values))
    monkeypatch.setattr(system_strip, "_texts", lambda *a, **k: None)
    without = np.asarray(draw(values))
    rows = np.nonzero((with_text != without).any(axis=(1, 2)))[0]
    assert len(rows) and all(r < 90 - 3 or r >= 180 + 3 for r in rows)
    assert with_text.shape == (270, 60, 3)


def test_system_strip_bars_follow_values():
    low = np.asarray(system_strip.classic((0, 0, 0, 0)))
    high = np.asarray(system_strip.classic((100, 0, 0, 100)))
    assert not (low[34:130, 6:26] == high[34:130, 6:26]).all()   # CPU oben links
    assert (low[34:130, 34:54] == high[34:130, 34:54]).all()     # RAM bleibt
    assert not (low[141:237, 34:54] == high[141:237, 34:54]).all()  # GPU 2 unten rechts
    none = np.asarray(system_strip.cockpit((None,) * 4))
    zero = np.asarray(system_strip.cockpit((0,) * 4))
    assert not (none == zero).all()                              # „–“ statt „0“


# --- Engine --------------------------------------------------------------------------------

def test_engine_draws_system_strip_and_redraws_only_on_change():
    rig, load = _system_rig("right")
    e = rig.engine
    e.redraw_all()
    assert load.active
    expected = system_strip.classic(load.v, (False,) * 3, ERROR_HEX)
    want = pixels(Display.RIGHT, to_rgb565(expected, Display.RIGHT.big_endian))
    assert (rig.last(Display.RIGHT) == want).all()
    left = pixels(Display.LEFT, to_rgb565(strip_image(
        [e.painter.strip_section(i, rig.clock()) for i in range(3)]), Display.LEFT.big_endian))
    assert (rig.last(Display.LEFT) == left).all()               # links weiter die Regler
    rig.draws.clear()
    e.tick()
    assert rig.count(Display.RIGHT) == 0                         # gleiche Werte: nichts
    load.v = (13, 34, 56, 78)
    e.tick()
    assert rig.count(Display.RIGHT) == 1


def test_sampling_only_while_shown_and_bright():
    rig, load = _system_rig("left")
    e = rig.engine
    assert load.active
    e.lock()
    assert not load.active
    e.unlock()
    assert load.active
    e.call("workspace", {"id": "ws2"})                           # zeigt nur Regler
    assert not load.active
    e.call("workspace", {"id": "ws1"})
    assert load.active
    assert e.start_saver("matrix")
    assert not load.active
    e.saver.stop()
    assert load.active
    e.device_connected = False
    e.tick()
    assert not load.active
    e.device_connected = True
    e.shutdown()
    assert not load.active
    unused = FakeLoad()
    Rig(system_load=unused)
    assert unused.switches == []                                 # nie eingeschaltet


def test_cockpit_system_strip_with_chaser():
    rig, load = _system_rig("right", device_look="cockpit")
    e = rig.engine
    e.look_frame()
    a = rig.last(Display.RIGHT)
    for _ in range(looks.SLOW_EVERY):
        e.look_frame()
    b = rig.last(Display.RIGHT)
    assert not (a[:, :2] == b[:, :2]).all()                     # Lauflicht an der Kante links
    assert (a[:, 4:] == b[:, 4:]).all()


def test_knob_error_flashes_on_system_strip():
    rig, _ = _system_rig("left")
    rig.engine.state.feedback.flashes[ControlRef("knob", 0)] = rig.clock() + 10
    rig.engine.tick()
    img = rig.last(Display.LEFT)
    assert tuple(img[45, 0]) == (0xf8, 0x20, 0x20)


# --- Profil und Editor --------------------------------------------------------------------

def test_profile_strip_modes_roundtrip_and_validation():
    ws = Workspace.from_json({"id": "a"})
    assert (ws.strip_left, ws.strip_right) == (STRIP_KNOBS, STRIP_KNOBS)   # alte Profile
    ws.strip_right = STRIP_SYSTEM
    d = ws.to_json()
    assert d["strip_left"] == "knobs" and d["strip_right"] == "system"
    assert Workspace.from_json(d).strip_right == STRIP_SYSTEM
    assert Workspace.from_json({"id": "a", "strip_left": "quatsch"}).strip_left == STRIP_KNOBS
    p = Profile.empty().to_json()
    p["workspaces"][0]["strip_right"] = "system"
    assert validate_profile_json(p) == []
    p["workspaces"][0]["strip_left"] = "balken"
    errors = validate_profile_json(p)
    assert len(errors) == 1 and "strip_left" in errors[0]


def test_editor_strips_menu_sets_workspace(window_rig):
    win = window_rig.win
    action = win.toolbar.strip_actions[("right", STRIP_SYSTEM)]
    assert not action.isChecked() and win.toolbar.strip_actions[("right", STRIP_KNOBS)].isChecked()
    action.trigger()
    win.flush()
    assert window_rig.store.load("default").workspaces[0].strip_right == STRIP_SYSTEM
    assert win.toolbar.strip_actions[("right", STRIP_SYSTEM)].isChecked()
    win.pages.set_strip_mode("right", STRIP_KNOBS)
    assert window_rig.engine.profile.workspaces[0].strip_right == STRIP_KNOBS
