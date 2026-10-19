"""Beruehrungen des mittleren Displays und der Leisten je Finger (ohne Qt).

* Leiste: Aufsetzen drueckt (eigene Tipp-Aktion ``Encoder.tap`` oder Regler-Druck), Abheben
  laesst los; solange der Finger liegt, leuchtet der Abschnitt (Cockpit).
* Feld: Aufsetzen markiert das Feld und startet ggf. eine Geste (``gestures``); Abheben auf
  demselben Feld tippt, weites Ziehen nach links/rechts wechselt die Seite (Ordnerseiten
  verlaesst man nur ueber „Zurück“), Abheben daneben bricht ab.
* R25: Eine Beruehrung, die vor einem Ansichtswechsel begann, loest nichts aus; R26: auch
  nicht, wenn das Feld inzwischen anders belegt ist (Inhalt verglichen).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..device.layout import ControlKind, ControlRef, touch_target
from ..device.protocol import TouchEvent
from ..profile.model import Assignment
from .controls import ControlResolver
from .gestures import MOVE_CANCEL_PX, Gesture, Gestures, same_assignment
from .ports import Clock, Redraw
from .state import EngineState

SWIPE_PX = 120  # so weit seitlich gezogen: Seite wechseln statt tippen
TOUCH, STRIP, KNOB = ControlKind.TOUCH, ControlKind.STRIP, ControlKind.KNOB


@dataclass
class Touch:
    """Ein aufgesetzter Finger."""
    x: int
    y: int
    target: ControlRef
    t: float
    cx: int = 0             # aktuelle Position (Ziehen)
    cy: int = 0
    gesture: bool = False   # dieser Finger gehoert zur Tipp-/Halte-Geste der Taste
    ignored: bool = False   # kam waehrend einer fremden Geste dazu (z. B. zweiter Finger)
    view: int = 0           # Ansicht beim Aufsetzen (R25: danach gewechselt -> nichts)
    a: Assignment | None = None  # Belegung beim Aufsetzen (R26: danach geaendert -> nichts)
    strip_tap: bool = False  # Leiste: eigene Tipp-Aktion (``Encoder.tap``) statt Regler-Druck


@dataclass(frozen=True)
class TouchActions:
    """Was Beruehrungen ausloesen: ``press``/``release`` wie ein Tastendruck, Regler-Druck
    ueber die Leiste (``knob_down``/``knob_up``), ``tap(feld, dauer)`` und die Navigation
    ``navigate(name, params)`` (Wischen)."""
    press: Callable[[ControlRef, dict | None], None]
    release: Callable[[ControlRef], None]
    knob_down: Callable[[ControlRef], None]
    knob_up: Callable[[ControlRef], None]
    tap: Callable[[int, float], None]
    navigate: Callable[[str, dict], None]


class TouchTracker:
    """Merkt sich jeden aufgesetzten Finger bis zum Abheben."""

    def __init__(self, state: EngineState, controls: ControlResolver, gestures: Gestures,
                 actions: TouchActions, *, clock: Clock, redraw: Redraw) -> None:
        self._state = state
        self._controls = controls
        self._gestures = gestures
        self._do = actions
        self._clock = clock
        self._redraw = redraw
        self._touches: dict[int, Touch] = {}

    def handle(self, ev: TouchEvent) -> None:
        if ev.down:
            self._down(ev)
        else:
            self._up(ev)

    def finger_on(self, finger: int, ref: ControlRef) -> bool:
        """Liegt ``finger`` (an seiner aktuellen Position) auf ``ref``?"""
        touch = self._touches.get(finger)
        return touch is not None and touch_target(touch.cx, touch.cy) == ref

    def strip_pressed(self, index: int) -> bool:
        """Liegt ein Finger auf Leistenabschnitt ``index``?"""
        ref = ControlRef(STRIP, index)
        return any(t.target == ref for t in self._touches.values())

    def clear(self) -> None:
        self._touches.clear()

    # --- Aufsetzen und Ziehen ------------------------------------------------------------

    def _down(self, ev: TouchEvent) -> None:
        touch = self._touches.get(ev.finger)
        if touch is not None:  # "an" kommt beim Ziehen wiederholt
            self._move(touch, ev)
            return
        target = touch_target(ev.x, ev.y)
        touch = self._touches[ev.finger] = Touch(ev.x, ev.y, target, self._clock(), ev.x, ev.y,
                                                 view=self._state.view_gen)
        if target.kind == STRIP:
            self._strip_down(touch)
        else:
            self._tile_down(touch, ev.finger)

    def _move(self, touch: Touch, ev: TouchEvent) -> None:
        touch.cx, touch.cy = ev.x, ev.y
        if touch.gesture and max(abs(ev.x - touch.x), abs(ev.y - touch.y)) > MOVE_CANCEL_PX:
            self._gestures.stop_hold(ControlRef(TOUCH, touch.target.index))

    def _strip_down(self, touch: Touch) -> None:
        target = touch.target
        tap = self._controls.strip_tap(target.index)
        touch.strip_tap = tap is not None
        if tap is not None:
            self._do.press(target, tap)
        else:
            self._do.knob_down(ControlRef(KNOB, target.index))
        self._redraw.now()  # Cockpit: Abschnitt leuchtet, solange der Finger liegt

    def _tile_down(self, touch: Touch, finger: int) -> None:
        index = touch.target.index
        a = touch.a = self._controls.tile(index)
        if a is None:
            return
        self._state.feedback.highlight.add(index)
        ref = ControlRef(TOUCH, index)
        g = self._gestures.get(ref)
        if g is not None:
            touch.gesture = self._gestures.press(ref, g)
            touch.ignored = not touch.gesture
        elif self._gestures.wants(a):
            touch.gesture = True
            self._gestures.start(ref, a, self._controls.state_key(ref), finger=finger)
        self._redraw.now()

    # --- Abheben -------------------------------------------------------------------------

    def _up(self, ev: TouchEvent) -> None:
        start = self._touches.pop(ev.finger, None)
        if start is None:
            return
        if start.target.kind == STRIP:
            if start.strip_tap:
                self._do.release(start.target)
            else:
                self._do.knob_up(ControlRef(KNOB, start.target.index))
        else:
            self._tile_up(start, ev)
        self._redraw.now()

    def _tile_up(self, start: Touch, ev: TouchEvent) -> None:
        index = start.target.index
        ref = ControlRef(TOUCH, index)
        g = self._gestures.get(ref) if start.gesture else None
        if start.gesture and g is None:
            self._do.release(ref)  # Geste verworfen (Ansichtswechsel): gehaltenes loslassen
        if not any(t.target == start.target for t in self._touches.values()):
            self._state.feedback.highlight.discard(index)  # sonst liegt noch ein Finger dort
        if start.view != self._state.view_gen:
            return  # R25: vor einem Ansichtswechsel begonnen -> loest nichts aus
        dx = ev.x - start.x
        if abs(dx) > SWIPE_PX:
            self._swipe(ref, g, dx)
        elif touch_target(ev.x, ev.y) == start.target:
            self._lift_on_tile(start, ref, g)
        elif g is not None:
            self._gestures.cancel(ref)

    def _swipe(self, ref: ControlRef, g: Gesture | None, dx: int) -> None:
        """Wie am Telefon: nach links wischen = naechste Seite (Seiten laufen im Kreis);
        Ordnerseiten verlaesst man nur ueber „Zurück“."""
        if g is not None:
            self._gestures.cancel(ref)  # Wischen gewinnt
        if not self._controls.in_folder():
            self._do.navigate("page_next" if dx < 0 else "page_previous", {})

    def _lift_on_tile(self, start: Touch, ref: ControlRef, g: Gesture | None) -> None:
        if g is not None:
            self._gestures.release(ref, g)
        elif not (start.gesture or start.ignored) and same_assignment(
                start.a, self._controls.tile(ref.index)):
            self._do.tap(ref.index, self._clock() - start.t)
