"""Geraete-Ereignisse -> Aktionen (ohne Qt): Tasten, Regler, Rad und Touch.

``InputRouter`` verteilt die Ereignisse: Tasten mit Doppeltippen/Halten ueber ``Gestures``,
Regler-Druecke mit Ebenen ueber ``KnobPress``, Drehungen ueber den ``Spinner`` des
``ActionDispatcher``, Beruehrungen ueber den ``TouchTracker``, Rad-Tippen ueber ``WheelTaps``.
Gesperrt, im Schlaf und waehrend einer Weck-Geste kommt hier nichts an (``power``).
"""
from __future__ import annotations

from collections.abc import Callable

from ..actions.base import Trigger
from ..device.layout import KNOB_FIRST, KNOB_LAST, ControlKind, ControlRef, control_for_button
from ..device.protocol import ButtonEvent, Event, RotateEvent, TouchEvent, WheelTouchEvent
from ..profile.model import Assignment
from .controls import ControlResolver
from .dispatch import ActionDispatcher
from .encoders import KnobPress, WheelTaps
from .gestures import GestureActions, Gestures
from .kinds import LIVE_TYPES, STOPWATCH, action_type
from .painter import layer_name
from .ports import EngineOptions, EnginePorts, Redraw
from .state import VALUE_S, EngineState
from .states import StateKey
from .touch import TouchActions, TouchTracker

KNOB, WHEEL, STRIP, TOUCH = ControlKind.KNOB, ControlKind.WHEEL, ControlKind.STRIP, ControlKind.TOUCH


class InputRouter:
    """Eingaben eines Geraets; ``call(name, params)`` ist die Navigation (Wischen)."""

    def __init__(self, ports: EnginePorts, state: EngineState,
                 controls: ControlResolver, dispatch: ActionDispatcher, *,
                 options: EngineOptions, call: Callable[[str, dict], None], redraw: Redraw,
                 guard: Callable[..., None]) -> None:
        self._state = state
        self._controls = controls
        self._dispatch = dispatch
        self._clock = ports.clock
        self._mono = ports.monotonic
        self._redraw = redraw
        # Doppeltippen/Halten (Schwellen global, ``settings``; siehe ``gestures``)
        self.gestures = Gestures(
            GestureActions(press=dispatch.press, release=dispatch.release,
                           trigger=dispatch.trigger, assignment=controls.assignment,
                           tap=self._gesture_tap, finger_on=self._finger_on),
            monotonic=ports.monotonic, call_later=ports.call_later, guard=guard,
            double_ms=options.double_ms, hold_ms=options.hold_ms)
        # Regler-Ebenen: Druecken = Ebene wechseln, Halten = press der Ebene
        self._knob_press = KnobPress(
            monotonic=ports.monotonic, call_later=ports.call_later,
            hold_ms=lambda: self.gestures.hold_ms,
            hold=lambda ref: dispatch.press(ref, controls.layer_press(ref)),
            hold_tap=lambda ref: dispatch.trigger(ref, controls.layer_press(ref)),
            cycle=lambda ref: self.cycle_layer(ref.index), release=dispatch.release,
            guard=guard)
        self._wheel_taps = WheelTaps()
        self.touch = TouchTracker(
            state, controls, self.gestures,
            TouchActions(press=dispatch.press, release=dispatch.release,
                         knob_down=self._knob_down, knob_up=self._knob_press.up, tap=self._tap,
                         navigate=call),
            clock=ports.clock, redraw=redraw)

    def route(self, event: Event) -> None:
        if isinstance(event, ButtonEvent):
            self._on_button(event)
        elif isinstance(event, RotateEvent):
            self._on_rotate(event)
        elif isinstance(event, TouchEvent):
            self.touch.handle(event)
        elif isinstance(event, WheelTouchEvent):
            self._on_wheel_touch(event)

    def forget(self) -> None:
        """Angefangene Gesten, Druecke und Beruehrungen vergessen (Sperre, Schlaf, Trennen)."""
        self.forget_gestures()
        self.touch.clear()
        self._wheel_taps.clear()
        self._state.feedback.highlight.clear()

    def forget_gestures(self) -> None:
        """Ansicht gewechselt: laufende Gesten und Regler-Druecke gehoeren zur alten Belegung
        (R24); geplante Rueckrufe laufen ins Leere."""
        self.gestures.clear()
        self._knob_press.clear()

    # --- Tasten und Regler ---------------------------------------------------------------

    def _on_button(self, ev: ButtonEvent) -> None:
        try:
            ref = control_for_button(ev.code)
        except KeyError:
            return
        if ref.kind == KNOB:
            if ev.pressed:
                self._knob_down(ref)
            else:
                self._knob_press.up(ref)
        elif ev.pressed:
            self._button_down(ref)
        else:
            g = self.gestures.get(ref)
            if g is not None:
                self.gestures.release(ref, g)
            else:
                self._dispatch.release(ref)

    def _button_down(self, ref: ControlRef) -> None:
        g = self.gestures.get(ref)
        if g is not None:
            self.gestures.press(ref, g)
            return
        a = self._controls.assignment(ref)
        if a is None:
            return
        key = self._controls.state_key(ref)
        if self.gestures.wants(a):
            self.gestures.start(ref, a, key)
            return
        # ohne Doppeltippen/Halten: sofort (hold_key bis zum Loslassen)
        action = self._controls.states.tap_action(a, key)
        self._dispatch.press(ref, action)
        self.after_tap(a, key, action)

    def _knob_down(self, ref: ControlRef) -> None:
        """Regler-Druck (Knopf oder Leiste): ohne Ebenen sofort, mit Ebenen entscheidet das
        Loslassen bzw. Halten (``KnobPress``)."""
        enc = self._controls.encoder(ref.index)
        if enc.layers:
            self._knob_press.down(ref)
        else:
            self._dispatch.press(ref, enc.press)

    def _on_rotate(self, ev: RotateEvent) -> None:
        if ev.code == 0:
            ref = ControlRef(WHEEL, 0)
        elif KNOB_FIRST <= ev.code <= KNOB_LAST:
            ref = ControlRef(KNOB, ev.code - KNOB_FIRST)
            self._knob_press.turned(ref)  # gedrueckt gedreht: kein Halten, kein Ebenenwechsel
        else:
            return
        self._dispatch.rotate(ref, ev.delta)

    def _on_wheel_touch(self, ev: WheelTouchEvent) -> None:
        """Tippen auf die Mitte des Raddisplays loest ``Wheel.tap`` aus."""
        if self._wheel_taps.touch(ev.finger, ev.x, ev.y, ev.down, self._mono(),
                                  self._state.view_gen):
            self._dispatch.trigger(ControlRef(WHEEL, 0), self._controls.wheel_tap())

    def cycle_layer(self, index: int) -> None:
        """Naechste Ebene; die Leiste zeigt „Ebene n/m · Name“ fuer ``VALUE_S``."""
        enc = self._controls.encoder(index)
        if not enc.layers:
            return
        self._controls.layers.cycle(self._controls.layer_key(index), enc, layer_name,
                                    self._clock() + VALUE_S)
        self._state.feedback.values.pop(index, None)  # Wert gehoerte zur alten Ebene
        self._dispatch.drop_rotation(ControlRef(KNOB, index))
        self._redraw.later(VALUE_S)
        self._redraw.now()

    # --- Tippen --------------------------------------------------------------------------

    def _tap(self, index: int, duration: float) -> None:
        """Feld ``index`` angetippt (Finger ``duration`` Sekunden aufgelegt)."""
        a = self._controls.tile(index)
        if a is None:
            return
        ref = ControlRef(TOUCH, index)
        key = self._controls.state_key(ref)
        action = self._controls.states.tap_action(a, key)
        if action_type(action) == STOPWATCH:
            self._controls.stopwatch(index).press(duration, self._clock())
            return
        self._dispatch.trigger(ref, action)
        self.after_tap(a, key, action)

    def after_tap(self, a: Assignment, key: StateKey, action: dict) -> None:
        """Manueller Zustand: nach dem Tippen weiterschalten (neues Bild zeichnen). Live-
        Kacheln (Uhr, Datum, Stoppuhr) loesen nichts aus und schalten nicht weiter."""
        if action_type(action) in LIVE_TYPES:
            return
        states = self._controls.states
        before = states.current(a, key)
        states.after_tap(a, key)
        if states.current(a, key) != before:
            self._redraw.now()

    def _gesture_tap(self, ref: ControlRef, a: Assignment, key: StateKey) -> None:
        """Einfaches Tippen nach einer Geste (Doppeltipp-Fenster abgelaufen o. ae.)."""
        action = self._controls.states.tap_action(a, key)
        self._dispatch.trigger(ref, action)
        self.after_tap(a, key, action)

    def _finger_on(self, finger: int, ref: ControlRef) -> bool:
        return self.touch.finger_on(finger, ref)

    # --- Wie am Geraet (API ``trigger``) -------------------------------------------------

    def activate(self, ref: ControlRef, which: Trigger = Trigger.TAP, *, steps: int = 0) -> bool:
        """Belegte Aktion (``tap``, ``double``, ``hold``, ``rotate``) einmal ausloesen wie am
        Geraet; Tippen schaltet einen manuellen Zustand weiter. Drehen rechnet wie am Geraet
        um (``invert``, ``factor``, links/rechts), Tippen auf einen Regler mit Ebenen wechselt
        die Ebene. ``False``, wenn nichts belegt ist."""
        if ref.kind == STRIP:
            tap = self._controls.strip_tap(ref.index)
            if tap is not None:
                if which == Trigger.TAP:
                    self._dispatch.trigger(ref, tap)
                return which == Trigger.TAP
            ref = ControlRef(KNOB, ref.index)
        if ref.kind == KNOB and which == Trigger.TAP and self._controls.encoder(ref.index).layers:
            self.cycle_layer(ref.index)
            return True
        if which == Trigger.ROTATE and ref.kind in (KNOB, WHEEL):
            return self._rotate_once(ref, steps)
        action = self._controls.action_for(ref, which)
        if action is None:
            return False
        a = self._controls.assignment(ref) if which == Trigger.TAP else None
        key = self._controls.state_key(ref) if a is not None else None
        self._dispatch.trigger(ref, action, steps=steps)
        if a is not None:
            self.after_tap(a, key, action)
        return True

    def _rotate_once(self, ref: ControlRef, steps: int) -> bool:
        turn = self._controls.turn(ref)
        calls = turn.calls(steps) if turn is not None else []
        for action, n in calls:
            self._dispatch.trigger(ref, action, steps=n)
        return bool(calls)
