"""Ersatz fuer Geraet, Tastatur, Executor, Prozessaufrufe und Uhren – je genau einmal.

``FakeDevice`` ist die Obermenge der frueheren Varianten (Rauchtest, API, Editor-Prozess,
Dynamic Mode, Sitzung): es zeichnet alles mit, was der Dienst sendet, und kann wie der echte
Geraete-Thread neu verbinden.
"""
from __future__ import annotations

import heapq
import itertools
import subprocess
import threading
import time

from neondeck.actions.base import ActionContext, Result

T0 = 1_760_000_000.0  # epoch seconds


class FakeDevice:
    """Ersatz fuer ``CTDevice`` (``device_factory`` der ``App``)."""

    def __init__(self, port_finder, on_event, on_state):
        self.on_event, self.on_state = on_event, on_state
        self.draws: list = []              # (Display, Daten)
        self.leds: list[dict] = []
        self.brightness: list[int] = []
        self.started = self.stopped = False
        self.serial = None
        self.reconnects = 0
        self.at_reconnect = None  # (Zeichnungen, Helligkeiten) beim Aufruf von reconnect

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def reconnect(self):
        """Sitzung zu, Thread verbindet neu (in einem eigenen Thread, wie der echte
        Geraete-Thread)."""
        self.reconnects += 1
        self.at_reconnect = (len(self.draws), len(self.brightness))

        def cycle():
            self.on_state(False)
            time.sleep(0.05)
            self.on_state(True)
        threading.Thread(target=cycle).start()

    def draw(self, display, data):
        self.draws.append((display, data))

    def set_leds(self, colors):
        self.leds.append(dict(colors))

    def set_brightness(self, level):
        self.brightness.append(level)

    def serial_number(self, timeout=0.0):
        return self.serial


class FakeKeyboard:
    """Ersatz fuer die uinput-Tastatur: merkt sich Tastenkombinationen und das Schliessen;
    ``log`` haelt Tippen/Druecken/Loslassen in Reihenfolge (auch zwischen Tastatur und Maus,
    wenn beide dieselbe Liste bekommen)."""

    closed = False

    def __init__(self, log=None):
        self.taps = []
        self.log = log if log is not None else []

    def tap(self, combo):
        self.taps.append(combo)
        self.log.append(("tap", combo))

    def press(self, combo):
        self.log.append(("press", combo))

    def release(self, combo):
        self.log.append(("release", combo))

    def close(self):
        self.closed = True


class FakeMouse:
    """Ersatz fuer die uinput-Maus: merkt sich jedes ``scroll``."""

    closed = False

    def __init__(self, log=None):
        self.log = log if log is not None else []

    def scroll(self, vertical=0, horizontal=0):
        self.log.append(("scroll", vertical, horizontal))

    def close(self):
        self.closed = True


class FakeExecutor:
    """Haelt Auftraege fest; der Test meldet Ergebnisse mit finish()."""

    def __init__(self, engine_call, on_result):
        self.engine_call = engine_call
        self.on_result = on_result
        self.calls = []      # alle je eingereichten (ref, action, steps, pressed)
        self.open = []       # noch nicht beendete
        self.shut = False

    def submit(self, ref, action, steps=0, pressed=True):
        self.calls.append((ref, action, steps, pressed))
        self.open.append((ref, action, steps, pressed))

    def finish(self, i=0, result=None):
        ref, *_ = self.open.pop(i)
        self.on_result(ref, result or Result(True))

    def shutdown(self):
        self.shut = True


class FakeRun:
    """Ersatz fuer ``ctx.run``: merkt argv (``calls``) und die Optionen (``options``);
    antwortet je Teiltext der Befehlszeile mit (Exit-Code, stdout)."""

    def __init__(self, answers=None, missing=()):
        self.calls = []
        self.options = []
        self.answers = answers or {}
        self.missing = missing

    def __call__(self, argv, **kw):
        if argv[0] in self.missing:
            raise FileNotFoundError(argv[0])
        self.calls.append(argv)
        self.options.append(kw)
        key = next((k for k in self.answers if k in " ".join(argv)), None)
        code, out = self.answers.get(key, (0, ""))
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr="boom" if code else "")


class FakeProc:
    """Was ``FakePopen`` zurueckgibt: Prozessnummer (0 = unbekannt) und Exit-Code."""

    def __init__(self, pid=0, code=0):
        self.pid = pid
        self.code = code

    def wait(self):
        return self.code


class FakePopen:
    """Merkt ``(argv, kw)``; mit ``pids`` bekommt jeder Start der Reihe nach eine Nummer,
    ``code`` ist der Exit-Code jedes Prozesses."""

    def __init__(self, missing=(), pids=(), code=0):
        self.calls = []
        self.missing = missing
        self.pids = list(pids)
        self.code = code

    def __call__(self, argv, **kw):
        if argv[0] in self.missing:
            raise FileNotFoundError(argv[0])
        self.calls.append((argv, kw))
        return FakeProc(self.pids.pop(0) if self.pids else 0, self.code)


def make_ctx(run=None, popen=None, keyboard=None, focus=None, *, engine_call=None, **extra):
    """``ActionContext`` mit Ersatz fuer ``run`` und ``popen`` (nie echte Prozesse);
    ``extra``: weitere Felder (``mouse``, ``place``, ``media_loop``, ``sleep``)."""
    return ActionContext(engine_call=engine_call or (lambda n, a: None), keyboard=keyboard,
                         run=run or FakeRun(), popen=popen or FakePopen(), focus=focus, **extra)


class Clock:
    """Feste Uhr; Tests stellen ``t`` selbst weiter."""

    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Timers:
    """``call_later`` mit Fake-Uhr: ``advance`` laesst die Zeit laufen und ruft faellige
    Rueckrufe in Zeitreihenfolge auf (gleichzeitige in der Reihenfolge des Einplanens)."""

    def __init__(self, clock):
        self.clock = clock
        self._seq = itertools.count()
        self.pending = []

    def __call__(self, delay, fn):
        heapq.heappush(self.pending, (self.clock.t + delay, next(self._seq), fn))

    def advance(self, dt):
        target = self.clock.t + dt
        while self.pending and self.pending[0][0] <= target + 1e-9:
            due, _, fn = heapq.heappop(self.pending)
            self.clock.t = max(self.clock.t, due)
            fn()
        self.clock.t = target
