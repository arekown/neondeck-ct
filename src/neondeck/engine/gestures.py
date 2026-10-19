"""Doppeltippen und Halten fuer Tasten (Touch, rund, eckig), ohne Qt.

Nur Tasten mit ``double`` oder ``hold`` laufen hierueber; alle anderen und der Regler-Druck
loesen in der Engine sofort aus wie bisher.

* Halten: ab ``hold_ms`` Druckdauer, noch waehrend gedrueckt (Touch: Finger noch auf der
  Taste); eine ``hold_key``-Aktion bleibt bis zum Loslassen gedrueckt.
* Ohne ``double`` tippt ein kurzes Druecken sofort beim Loslassen, mit ``double`` erst nach
  ``double_ms`` ohne zweites Druecken.
* Doppeltippen: Taste beim zweiten Druecken, Touch beim zweiten Abheben (Wischen gewinnt).
* Einfaches Tippen nach einer Geste laeuft wie ``Engine.trigger`` (Druecken + Loslassen).
* Ohne ``call_later`` entscheidet beim Loslassen die Druckdauer; Doppeltippen gibt es dann
  nicht.

Geplante Rueckrufe tragen ein Token: nur der zuletzt geplante einer Geste wirkt. Eine Geste,
deren Taste inzwischen anders belegt ist (Inhalt verglichen, nicht das Objekt: Speichern im
Editor laesst gleiche Belegungen weiterlaufen, R26), gilt als veraltet und wird verworfen; die Engine verwirft bei jedem Ansichtswechsel ohnehin alle
(``clear``). Gehaltene ``hold_key``-Aktionen laesst die Engine trotzdem beim Loslassen los.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..core.values import EPS
from ..device.layout import ControlKind, ControlRef
from ..profile.model import Assignment
from .kinds import STOPWATCH, action_type, typed
from .states import StateKey

DOUBLE_MS = 300           # Doppeltippen: Fenster nach dem ersten Loslassen
HOLD_MS = 500             # Halten: ab so langer Druckdauer
MOVE_CANCEL_PX = 24       # so weit bewegt: kein Halten bzw. kein Rad-Tippen mehr (Wischen gewinnt)


def same_assignment(a: Assignment | None, b: Assignment | None) -> bool:
    """Gleiche Belegung? Nach dem Speichern im Editor sind alle Belegungen neue Objekte;
    verglichen wird darum der Inhalt (R26)."""
    return a is b or (a is not None and b is not None and a.to_json() == b.to_json())


class Phase(Enum):
    """Phase einer Geste."""
    DOWN = "down"    # erstes Druecken, Halten-Uhr laeuft
    HELD = "held"    # Halten ausgeloest
    WAIT = "wait"    # losgelassen, Doppeltipp-Fenster laeuft
    DOWN2 = "down2"  # zweites Druecken


@dataclass
class Gesture:
    """Laufende Geste einer Taste (``phase`` siehe ``Phase``)."""
    a: Assignment
    key: StateKey
    phase: Phase
    t: float
    finger: int | None = None  # Touch: der Finger dieser Geste
    token: object = None          # gilt nur der zuletzt geplante Rueckruf


@dataclass(frozen=True)
class GestureActions:
    """Ausloeser, die die Engine hereinreicht:

    * ``press(ref, action)`` / ``release(ref)``: wie ein Tastendruck (``hold_key`` gehalten),
    * ``trigger(ref, action)``: einmal Druecken + Loslassen,
    * ``assignment(ref)``: aktuelle Belegung (aendert sie sich, ist die Geste veraltet),
    * ``tap(ref, assignment, key)``: einfaches Tippen (Zustandsaktion, Zustand weiter),
    * ``finger_on(finger, ref)``: liegt der Finger noch auf der Taste?"""
    press: Callable[[ControlRef, dict | None], None]
    release: Callable[[ControlRef], None]
    trigger: Callable[[ControlRef, dict | None], None]
    assignment: Callable[[ControlRef], Assignment | None]
    tap: Callable[[ControlRef, Assignment, StateKey], None]
    finger_on: Callable[[int, ControlRef], bool]


class Gestures:
    """Gesten je Bedienelement; ``actions`` loest aus, ``guard(fn, *args)`` fuehrt geplante
    Rueckrufe abgesichert aus."""

    def __init__(self, actions: GestureActions, *, monotonic: Callable[[], float],
                 call_later: Callable[[float, Callable[[], None]], None] | None,
                 guard: Callable[..., None],
                 double_ms: int = DOUBLE_MS, hold_ms: int = HOLD_MS) -> None:
        self._mono = monotonic
        self._call_later = call_later
        self._do = actions
        self._guard = guard
        self.double_ms = double_ms
        self.hold_ms = hold_ms
        self._active: dict[ControlRef, Gesture] = {}

    @staticmethod
    def wants(a: Assignment) -> bool:
        """Nur Tasten mit Doppeltippen oder Halten warten; Stoppuhr-Kacheln messen selbst."""
        return (typed(a.double) or typed(a.hold)) and action_type(a.action) != STOPWATCH

    def get(self, ref: ControlRef) -> Gesture | None:
        """Laufende Geste der Taste; eine veraltete wird verworfen (``None``)."""
        g = self._active.get(ref)
        if g is not None and self._stale(ref, g):
            del self._active[ref]
            return None
        return g

    def _stale(self, ref: ControlRef, g: Gesture) -> bool:
        """Veraltet, wenn die Taste jetzt anders belegt ist; bei gleichem Inhalt (Editor hat
        gespeichert) gilt fortan das neue Objekt."""
        a = self._do.assignment(ref)
        if a is g.a:
            return False
        if not same_assignment(a, g.a):
            return True
        g.a = a
        return False

    def clear(self) -> None:
        """Alles vergessen; geplante Rueckrufe laufen dann ins Leere."""
        self._active.clear()

    def _schedule(self, ref: ControlRef, g: Gesture, delay_ms: int,
                  fn: Callable[[ControlRef, object], None]) -> None:
        g.token = token = object()
        if self._call_later is not None:
            self._call_later(delay_ms / 1000, lambda: self._guard(fn, ref, token))

    def start(self, ref: ControlRef, a: Assignment, key: StateKey,
              finger: int | None = None) -> None:
        g = self._active[ref] = Gesture(a, key, Phase.DOWN, self._mono(), finger)
        if typed(a.hold):
            self._schedule(ref, g, self.hold_ms, self._hold_due)

    def press(self, ref: ControlRef, g: Gesture) -> bool:
        """Erneutes Druecken waehrend einer Geste: im Doppeltipp-Fenster = Doppeltippen
        (Taste: sofort; Touch: beim Abheben, damit Wischen gewinnt). Sonst ignoriert
        (z. B. zweiter Finger). ``True``, wenn das Druecken zur Geste gehoert."""
        if g.phase != Phase.WAIT:
            return False
        g.phase, g.token = Phase.DOWN2, None
        if ref.kind != ControlKind.TOUCH:
            self._do.press(ref, g.a.double)
        return True

    def release(self, ref: ControlRef, g: Gesture) -> None:
        if g.phase in (Phase.HELD, Phase.DOWN2):
            del self._active[ref]
            if g.phase == Phase.DOWN2 and ref.kind == ControlKind.TOUCH:
                self._do.trigger(ref, g.a.double)
            else:
                self._do.release(ref)  # gehaltene hold_key-Aktion loslassen
        elif g.phase == Phase.DOWN:
            if self._call_later is None:  # ohne Zeitgeber: die Druckdauer entscheidet
                del self._active[ref]
                if typed(g.a.hold) and self._mono() - g.t >= self.hold_ms / 1000 - EPS:
                    self._do.trigger(ref, g.a.hold)
                else:
                    self._do.tap(ref, g.a, g.key)
            elif typed(g.a.double):
                g.phase = Phase.WAIT
                self._schedule(ref, g, self.double_ms, self._double_due)
            else:  # nur Halten belegt: kurzes Druecken tippt sofort beim Loslassen
                del self._active[ref]
                self._do.tap(ref, g.a, g.key)

    def cancel(self, ref: ControlRef) -> None:
        """Geste abbrechen (Wischen, Abheben neben der Taste). Ein schon fertiges erstes
        Tippen (Touch: zweites Beruehren wurde zum Wischen) loest noch aus."""
        g = self._active.pop(ref, None)
        if g is None:
            return
        if g.phase == Phase.DOWN2 and ref.kind == ControlKind.TOUCH:
            self._do.tap(ref, g.a, g.key)
        elif g.phase in (Phase.HELD, Phase.DOWN2):
            self._do.release(ref)

    def stop_hold(self, ref: ControlRef) -> None:
        """Finger bewegt sich (Wischen beginnt): kein Halten mehr fuer diese Geste."""
        g = self._active.get(ref)
        if g is not None and g.phase == Phase.DOWN:
            g.token = None

    def _hold_due(self, ref: ControlRef, token: object) -> None:
        g = self.get(ref)
        if g is None or g.token is not token or g.phase != Phase.DOWN:
            return
        if g.finger is not None and not self._do.finger_on(g.finger, ref):
            return  # Touch: Finger muss noch auf der Taste liegen
        g.phase, g.token = Phase.HELD, None
        self._do.press(ref, g.a.hold)  # hold_key bleibt gedrueckt bis zum Loslassen

    def _double_due(self, ref: ControlRef, token: object) -> None:
        g = self.get(ref)
        if g is None or g.token is not token or g.phase != Phase.WAIT:
            return
        del self._active[ref]
        self._do.tap(ref, g.a, g.key)
