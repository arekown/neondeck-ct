"""Hell und dunkel (ohne Qt): Sperre, Display-Schlaf, Weck-Geste, Bildschirmschoner und der
Takt des Geraete-Looks.

* ``PowerState``: Sperre (alles schwarz, Eingaben ignoriert) und Display-Schlaf nach
  ``display_sleep_min`` Minuten ohne Eingabe; die erste Eingabe danach weckt nur.
* ``WakeGuard``: Rest der Weck-Geste (Taste bis Loslassen, Finger bis Abheben, Dreh-Schwung bis
  zur Pause) und alles, was in den ``WAKE_GRACE_S`` danach neu beginnt, wird verworfen.
* ``ScreensaverRunner``: Bildschirmschoner nach ``minutes`` Minuten; der Dienst holt die
  Bilder ueber ``frame`` ab, solange ``on_saver(True)`` gilt.
* ``LookClock``: aktueller Look (``looks``) und seine Bildnummer; animiert holt der Dienst die
  Bilder ueber ``step``, solange ``on_animate(True)`` gilt (nicht dunkel, kein Schoner).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from PIL import Image

from ..core.guard import call_logged
from ..device.layout import Display
from ..device.protocol import ButtonEvent, Event, RotateEvent, TouchEvent, WheelTouchEvent
from ..render import savers
from ..render.look import FRAME_S
from .looks import make_look
from .ports import EngineHooks, EnginePorts, Look, Redraw
from .state import EngineState

log = logging.getLogger(__name__)

WAKE_GRACE_S = 0.3        # nach dem Wecken: neue Eingaben anderer Elemente noch verwerfen
WAKE_ROTATE_GAP_S = 0.4   # weckender Dreh-Schwung endet erst nach so langer Pause
SAVER_MIN_GAP_S = 0.04    # Bildschirmschoner: mindestens so viel Pause zwischen zwei Bildern
SAVER_LED_S = 0.2         # LEDs hoechstens so oft neu setzen
SAVER_IDLE_S = 0.25       # stehendes Bild: so oft nachsehen, ob sich etwas aendert
STATS_S = 5.0             # nach so vielen Sekunden einmal Bilder/s ins Log
LOOK_MIN_GAP_S = 0.04     # Geraete-Look: mindestens so viel Pause zwischen zwei Bildern
LOOK_IDLE_S = 0.5         # Geraet getrennt: so oft nachsehen, ob es wieder da ist


class Screen(Protocol):
    """Was Schlaf und Schoner vom ``DisplayPainter`` brauchen."""

    def send(self, display: Display, img: Image.Image) -> None: ...

    def show_leds(self, colors: dict[int, tuple]) -> None: ...

    def blank(self) -> None: ...

    def forget(self) -> None: ...


class FrameStats:
    """Bilder je Sekunde und Zeichenzeit; einmal nach ``STATS_S`` ins Log."""

    def __init__(self, what: str, monotonic: Callable[[], float]) -> None:
        self._what = what  # z. B. „Bildschirmschoner %s“
        self._mono = monotonic
        self.restart()

    def restart(self) -> None:
        self.t0 = self._mono()
        self._frames, self._busy, self._logged = 0, 0.0, False

    def add(self, name: str, busy: float, now: float) -> None:
        self._frames += 1
        self._busy += busy
        if not self._logged and now - self.t0 >= STATS_S:
            self._logged = True
            log.info(self._what + ": %.1f Bilder/s, %.0f ms je Bild", name,
                     self._frames / (now - self.t0), 1000 * self._busy / self._frames)


class WakeGuard:
    """Merkt sich die weckende Geste und die Gnadenfrist danach."""

    def __init__(self) -> None:
        self._grace_until = float("-inf")
        self._buttons: set[int] = set()
        self._fingers: set[int] = set()
        self._wheel: set[int] = set()  # Finger auf dem Raddisplay
        self._spins: dict[int, float] = {}

    def begin(self, now: float) -> None:
        self._grace_until = now + WAKE_GRACE_S

    def clear(self) -> None:
        self._grace_until = float("-inf")
        self._buttons.clear()
        self._fingers.clear()
        self._wheel.clear()
        self._spins.clear()

    def swallowed(self, event: Event, now: float) -> bool:
        """Gehoert ``event`` zu einer Weck-Geste (oder beginnt in der Gnadenfrist)? Dann wird
        die Geste vorgemerkt und das Ereignis verworfen."""
        in_grace = now < self._grace_until
        if isinstance(event, RotateEvent):
            return self._spin(event.code, now, in_grace)
        held = self._held(event)
        if held is None:
            return in_grace
        keys, key, down = held
        if key in keys:
            if not down:
                keys.discard(key)
            return True
        if in_grace and down:
            keys.add(key)
            return True
        return False

    def _held(self, event: Event) -> tuple[set[int], int, bool] | None:
        """(vorgemerkte, Schluessel, gedrueckt) fuer Tasten, Finger und Rad-Finger."""
        if isinstance(event, ButtonEvent):
            return self._buttons, event.code, event.pressed
        if isinstance(event, TouchEvent):
            return self._fingers, event.finger, event.down
        if isinstance(event, WheelTouchEvent):
            return self._wheel, event.finger, event.down
        return None

    def _spin(self, code: int, now: float, in_grace: bool) -> bool:
        last = self._spins.get(code)
        if in_grace or (last is not None and now - last < WAKE_ROTATE_GAP_S):
            self._spins[code] = now
            return True
        self._spins.pop(code, None)
        return False


class ScreensaverRunner:
    """Bildschirmschoner (``render.savers``): ``name`` und ``options`` (Diashow:
    ``{"folder": str, "slide_s": int}``) setzt der Dienst; ``minutes`` = 0 heisst aus."""

    def __init__(self, state: EngineState, ports: EnginePorts,
                 hooks: EngineHooks, screen: Screen, *, forget_input: Callable[[], None],
                 redraw_all: Callable[[], None], mode_changed: Callable[[], None]) -> None:
        self._state = state
        self._clock = ports.clock
        self._mono = ports.monotonic
        self._hooks = hooks
        self._screen = screen
        self._forget_input = forget_input
        self._redraw_all = redraw_all
        self._mode_changed = mode_changed
        self.name = "cockpit"
        self.minutes = 0
        self.options: dict = {}
        self._saver: savers.Saver | None = None
        self._leds_at = float("-inf")
        self._stats = FrameStats("Bildschirmschoner %s", ports.monotonic)

    @property
    def active(self) -> bool:
        return self._saver is not None

    def due(self, idle: float) -> bool:
        """Nach ``idle`` Sekunden ohne Eingabe faellig?"""
        return self.minutes > 0 and not self._state.dark and self._saver is None \
            and idle >= self.minutes * 60

    def start(self, name: str | None = None) -> bool:
        """Bildschirmschoner starten (auch als Vorschau); gesperrt oder im Schlaf: nein.
        Die erste Eingabe danach beendet ihn, ohne eine Aktion auszuloesen."""
        if self._state.dark:
            return False
        if self._saver is not None:
            self.stop(redraw=False)
        self._forget_input()
        self._saver = savers.make(name or self.name, clock=self._clock,
                                        options=self.options)
        self._state.saver_on = True
        self._leds_at = float("-inf")
        self._stats.restart()
        log.info("Bildschirmschoner %s gestartet", self._saver.name)
        self._notify(True)
        self._mode_changed()
        return True

    def stop(self, *, redraw: bool = True) -> None:
        if self._saver is None:
            return
        saver, self._saver = self._saver, None
        self._state.saver_on = False
        try:
            saver.close()
        except Exception:
            log.exception("Bildschirmschoner %s nicht sauber beendet", saver.name)
        self._screen.forget()
        self._notify(False)
        if redraw and not self._state.dark:
            self._redraw_all()
        self._mode_changed()

    def frame(self) -> float | None:
        """Ein Bild zeichnen; liefert die Pause bis zum naechsten (``None``: Schoner aus).
        Die Pause ist mindestens so lang wie das Zeichnen selbst – das Geraet ist hoechstens
        zur Haelfte belegt, Eingaben kommen dazwischen sofort an."""
        saver = self._saver
        if saver is None or self._state.dark:
            return None
        start = self._mono()
        try:
            frame = saver.frame(start - self._stats.t0)
        except Exception:
            log.exception("Bildschirmschoner %s: Bild nicht berechnet", saver.name)
            self.stop()
            return None
        if not frame.changed:  # stehendes Bild (Diashow): nichts senden, seltener nachsehen
            return SAVER_IDLE_S
        self._show(frame)
        now = self._mono()
        if frame.leds and now - self._leds_at >= SAVER_LED_S:
            self._leds_at = now
            self._screen.show_leds(frame.leds)
        busy = now - start
        self._stats.add(saver.name, busy, now)
        return max(SAVER_MIN_GAP_S, busy)

    def _show(self, frame: savers.Frame) -> None:
        """Die Flaeche (Leiste, Mitte, Leiste nebeneinander) auf die Displays verteilen."""
        canvas, strip, center = frame.canvas, Display.LEFT.width, Display.CENTER.width
        self._screen.send(Display.LEFT, canvas.crop((0, 0, strip, Display.LEFT.height)))
        self._screen.send(Display.CENTER, canvas.crop((strip, 0, strip + center,
                                                       Display.CENTER.height)))
        self._screen.send(Display.RIGHT, canvas.crop((strip + center, 0, canvas.width,
                                                      Display.RIGHT.height)))
        self._screen.send(Display.WHEEL, frame.wheel)

    def _notify(self, active: bool) -> None:
        if self._hooks.on_saver is not None:
            call_logged(self._hooks.on_saver, active,
                        what="Bildschirmschoner-Wechsel nicht gemeldet", logger=log)


class PowerState:
    """Sperre und Display-Schlaf; ``display_sleep_min`` = 0 heisst kein Schlaf."""

    def __init__(self, state: EngineState, ports: EnginePorts,
                 hooks: EngineHooks, screen: Screen, saver: ScreensaverRunner, *,
                 forget_input: Callable[[], None], redraw_all: Callable[[], None],
                 mode_changed: Callable[[], None]) -> None:
        self._state = state
        self._mono = ports.monotonic
        self._hooks = hooks
        self._screen = screen
        self._saver = saver
        self._forget_input = forget_input
        self._redraw_all = redraw_all
        self._mode_changed = mode_changed
        self.display_sleep_min = 0
        self._last_input = self._mono()
        self.wake_guard = WakeGuard()

    def intercept(self, event: Event) -> bool:
        """Vor jeder Eingabe: ``True``, wenn sie nichts ausloesen darf. Gesperrt: jede;
        Display-Schlaf oder Schoner: die erste weckt nur – samt ihrer ganzen Geste und allem,
        was in den ``WAKE_GRACE_S`` danach neu beginnt."""
        if self._state.locked:
            return True
        now = self._mono()
        self._last_input = now
        if self._state.asleep or self._state.saver_on:
            self.wake()
            self.wake_guard.begin(now)
            self.wake_guard.swallowed(event, now)  # merkt die weckende Geste vor
            return True
        return self.wake_guard.swallowed(event, now)

    def idle_check(self) -> bool:
        """Jede Sekunde: nach ``display_sleep_min`` Minuten ohne Eingabe Display-Schlaf, nach
        ``saver.minutes`` der Bildschirmschoner (der Schlaf gewinnt, wenn er frueher oder
        gleichzeitig dran ist). ``True``, wenn eines davon begonnen hat."""
        idle = self._mono() - self._last_input
        if self.display_sleep_min > 0 and not self._state.dark \
                and idle >= self.display_sleep_min * 60:
            self.sleep_display()
            return True
        if self._saver.due(idle):
            self._saver.start()
            return True
        return False

    def note_activity(self) -> None:
        """Schlafuhr neu starten (Eingabe, Aufwachen, neue Einstellung)."""
        self._last_input = self._mono()

    def lock(self) -> None:
        """Bildschirm gesperrt: gehaltene Tasten loslassen, Displays schwarz, LEDs aus, alle
        Eingaben ignorieren bis ``unlock``."""
        if self._state.locked:
            return
        was = self._state.dark
        self._forget_input()
        self._state.locked = True  # vor dem Schoner-Ende: der Look-Takt startet dazwischen nicht
        self._saver.stop(redraw=False)
        self._screen.blank()
        self._report_dark(was)
        self._mode_changed()

    def unlock(self) -> None:
        """Entsperrt: alles neu zeichnen (weckt auch einen Display-Schlaf)."""
        if not self._state.locked:
            return
        self._state.locked = False
        self._state.asleep = False
        self.note_activity()
        self._redraw_all()
        self._report_dark(True)
        self._mode_changed()

    def sleep_display(self) -> None:
        """Display-Schlaf: Displays schwarz, LEDs aus; die erste Eingabe danach weckt nur."""
        if self._state.dark:
            return
        self._forget_input()
        self._state.asleep = True
        self._saver.stop(redraw=False)
        self._screen.blank()
        self._report_dark(False)
        self._mode_changed()

    def wake(self, *, redraw: bool = True) -> None:
        """Display-Schlaf beenden und neu zeichnen (gesperrt bleibt es schwarz).

        ``redraw=False`` (nach dem Standby): nur den Zustand loeschen, nichts senden und nichts
        melden – das folgende Wiederverbinden sendet Helligkeit und alle Displays. Beendet
        auch den Bildschirmschoner."""
        self.note_activity()
        if self._saver.active:
            self._saver.stop(redraw=redraw and not self._state.asleep)
        if not self._state.asleep:
            return
        was = self._state.dark
        self._state.asleep = False
        if redraw:
            self._redraw_all()
            self._report_dark(was)
        self._mode_changed()

    def _report_dark(self, was: bool) -> None:
        dark = self._state.dark
        if dark == was or self._hooks.on_dark is None:
            return
        call_logged(self._hooks.on_dark, dark, what="Wechsel hell/dunkel nicht gemeldet",
                    logger=log)


class LookClock:
    """Aktueller Look (Strategie, ``ports.Look``) und die Bildnummer seiner Animation."""

    def __init__(self, state: EngineState, ports: EnginePorts, hooks: EngineHooks,
                 look_name: str, *, redraw: Redraw) -> None:
        self._state = state
        self._mono = ports.monotonic
        self._hooks = hooks
        self._redraw = redraw
        self.look: Look = make_look(look_name)
        self.frame = 0
        self.animating = False
        self._stats = FrameStats("Geraete-Look %s", ports.monotonic)

    def switch(self, name: str) -> bool:
        """Anderen Look nehmen (Animation von vorn); ``False``, wenn es schon dieser ist."""
        if name == self.look.name:
            return False
        self.look = make_look(name)
        self.frame = 0
        self._stats.restart()
        return True

    def update(self) -> None:
        """Takt an/aus melden: nur mit animiertem Look, nicht dunkel, kein Schoner."""
        want = self.look.animated and self._state.showing
        if want == self.animating:
            return
        self.animating = want
        if self._hooks.on_animate is not None:
            call_logged(self._hooks.on_animate, want,
                        what="Takt des Geraete-Looks nicht gemeldet", logger=log)

    def step(self) -> float | None:
        """Naechstes Bild des Looks zeichnen (nur Geaendertes wird gesendet); liefert die
        Pause bis zum naechsten (``None``: kein Takt). Wie beim Bildschirmschoner ist die Pause
        mindestens so lang wie das Zeichnen – Eingaben kommen dazwischen sofort an und zeichnen
        selbst (dieselbe Bildnummer, nichts doppelt)."""
        if not self.animating:
            return None
        if not self._state.device_connected:
            return LOOK_IDLE_S
        start = self._mono()
        self.frame += 1
        self._redraw.now()
        now = self._mono()
        busy = now - start
        self._stats.add(self.look.name, busy, now)
        return max(LOOK_MIN_GAP_S, busy, FRAME_S - busy)
