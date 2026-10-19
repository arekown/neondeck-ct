"""Regler und Rad, ohne Qt: Drehungen sammeln, Schritte umrechnen, Ebenen, Rad-Tippen.

* Sammeln (Review Focus 5): Drehereignisse eines Reglers/Rads werden addiert. Mit
  ``call_later`` wartet die erste Drehung ``ROTATE_WINDOW_S`` auf weitere, ohne fuehrt sie
  sofort aus. Solange Aktionen laufen, wird weiter gesammelt und nichts neu eingereiht; erst
  das letzte Ergebnis (``done``) gibt das Gesammelte als naechste Ausfuehrung frei.
* Schritte (``Turn``): Summe × (−1 bei ``invert``) × ``factor``. Ist fuer die Richtung
  ``left``/``right`` belegt, laeuft diese Aktion |Schritte|-mal nacheinander in der Spur des
  Bedienelements, hoechstens ``MAX_REPEAT``-mal je Ausfuehrung (der Rest wird verworfen,
  damit schnelles Drehen mit hohem Faktor keine Flut von Tastendruecken ausloest); sonst
  ``rotate`` einmal mit ``steps``.
* Ebenen (``Layers``, ``KnobPress``): Regler mit ``layers`` wechseln beim kurzen Druecken
  die Ebene (zyklisch, je Profil/Arbeitsbereich/Regler); Halten ab ``hold_ms`` fuehrt
  ``press`` der aktiven Ebene aus (``hold_key`` bleibt bis zum Loslassen gedrueckt). Mit
  Ebenen gelten ``rotate``/``left``/``right``/``press``/``label`` der Ebene, ``invert``,
  ``factor`` und ``strip`` des Reglers.
* Rad-Tippen (``WheelTaps``): Aufsetzen nahe der Mitte, kurz und ohne Ziehen.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

from ..core.i18n import N_, tr
from ..core.values import EPS
from ..device.layout import WHEEL_SIZE, ControlRef
from ..profile.model import Encoder, EncoderLayer
from .gestures import MOVE_CANCEL_PX
from .kinds import typed

log = logging.getLogger(__name__)

ROTATE_WINDOW_S = 0.03  # Drehungen so lange sammeln (nur mit call_later)
MAX_REPEAT = 20         # links/rechts: hoechstens so oft je Ausfuehrung
WHEEL_CENTER = WHEEL_SIZE // 2
TAP_RADIUS_PX = 60      # Rad-Tippen: Aufsetzen naeher als so an der Mitte
TAP_MAX_S = 0.3         # ... kuerzer als so und weniger als ``MOVE_CANCEL_PX`` gezogen
TOUCH_STALE_S = 2.0     # Rad-Beruehrung ohne Abheben gilt danach als verloren


@dataclass(frozen=True)
class Turn:
    """Drehbelegung eines Reglers/Rads (bzw. seiner aktiven Ebene)."""
    rotate: dict | None = None
    left: dict | None = None
    right: dict | None = None
    invert: bool = False
    factor: int = 1

    @property
    def assigned(self) -> bool:
        return typed(self.rotate) or typed(self.left) or typed(self.right)

    def calls(self, delta: int) -> list[tuple[dict, int]]:
        """Auszufuehrende (Aktion, steps) fuer ``delta`` Rastungen."""
        steps = delta * (-1 if self.invert else 1) * self.factor
        if not steps:
            return []
        single = self.right if steps > 0 else self.left
        if typed(single):
            if abs(steps) > MAX_REPEAT:
                log.info("Drehen: %d von %d Schritten verworfen (hoechstens %d je Ausfuehrung)",
                         abs(steps) - MAX_REPEAT, abs(steps), MAX_REPEAT)
            return [(single, 0)] * min(abs(steps), MAX_REPEAT)
        return [(self.rotate, steps)] if typed(self.rotate) else []

    @property
    def first(self) -> dict | None:
        """Erste belegte Aktion (``rotate``, sonst ``right``, sonst ``left``)."""
        return next((a for a in (self.rotate, self.right, self.left) if typed(a)), None)


@dataclass
class Spin:
    """Drehungen eines Reglers/Rads, die noch nicht ausgefuehrt sind."""
    pending: int = 0
    running: int = 0       # eingereichte, noch nicht beendete Aktionen
    scheduled: bool = False


class Spinner:
    """Sammelt Drehungen je Bedienelement. Die Engine reicht herein:

    * ``turn(ref)``: aktuelle Drehbelegung (``None`` = nichts belegt),
    * ``submit(ref, action, steps)``: im Executor einreihen; ``False``, wenn das nicht ging."""

    def __init__(self, *, call_later: Callable[[float, Callable[[], None]], None] | None,
                 turn: Callable[[ControlRef], Turn | None],
                 submit: Callable[[ControlRef, dict, int], bool]) -> None:
        self._call_later = call_later
        self._turn = turn
        self._submit = submit
        self._spins: dict[ControlRef, Spin] = {}

    def rotate(self, ref: ControlRef, delta: int) -> None:
        if self._turn(ref) is None:
            return
        spin = self._spins.setdefault(ref, Spin())
        spin.pending += delta
        if spin.running or spin.scheduled:
            return  # weiter sammeln, nicht neu einreihen (Review Focus 5)
        if self._call_later is not None:
            spin.scheduled = True
            self._call_later(ROTATE_WINDOW_S, lambda: self.flush(ref))
        else:
            self.flush(ref)

    def flush(self, ref: ControlRef) -> None:
        spin = self._spins.get(ref)
        if spin is None:
            return
        spin.scheduled = False
        if spin.running:
            return
        delta, spin.pending = spin.pending, 0
        turn = self._turn(ref)
        for action, steps in turn.calls(delta) if turn is not None else []:
            spin.running += 1  # vor submit: ein Executor darf das Ergebnis sofort melden
            if not self._submit(ref, action, steps):
                spin.running -= 1
                break

    def done(self, ref: ControlRef) -> None:
        """Ergebnis einer Drehung ist da; nach dem letzten: Gesammeltes ausfuehren."""
        spin = self._spins.get(ref)
        if spin is not None:
            spin.running = max(0, spin.running - 1)
            if not spin.running and spin.pending:
                self.flush(ref)

    def drop_pending(self, ref: ControlRef | None = None) -> None:
        """Gesammelte Drehungen (aller oder eines Bedienelements) gehoeren zur alten
        Belegung und werden verworfen."""
        for r, spin in self._spins.items():
            if ref is None or r == ref:
                spin.pending = 0


# --- Ebenen ---------------------------------------------------------------------------

LayerKey = tuple  # (Profil-ID, Arbeitsbereich-ID, Regler)
NOTICE = N_("Ebene {n}/{m} · {name}")


class Layers:
    """Aktive Ebene je (Profil, Arbeitsbereich, Regler) und der Hinweis nach dem Wechsel.
    Gibt es weniger Ebenen als gemerkt (Editor), zaehlt der Rest der Division."""

    def __init__(self) -> None:
        self._index: dict[LayerKey, int] = {}
        self._notice: dict[LayerKey, tuple[str, float]] = {}

    def index(self, key: LayerKey, enc: Encoder) -> int:
        return self._index.get(key, 0) % len(enc.layers) if enc.layers else 0

    def active(self, key: LayerKey, enc: Encoder) -> EncoderLayer | None:
        return enc.layers[self.index(key, enc)] if enc.layers else None

    def cycle(self, key: LayerKey, enc: Encoder, name: Callable[[int, EncoderLayer], str],
              until: float) -> None:
        """Naechste Ebene (zyklisch); ``name(i, ebene)`` fuer den Hinweis bis ``until``."""
        if not enc.layers:
            return
        i = (self.index(key, enc) + 1) % len(enc.layers)
        self._index[key] = i
        self._notice[key] = (tr(NOTICE, n=i + 1, m=len(enc.layers),
                                      name=name(i, enc.layers[i])), until)

    def notice(self, key: LayerKey, now: float) -> str | None:
        """Hinweis „Ebene n/m · Name“, solange er gilt."""
        item = self._notice.get(key)
        if item is None:
            return None
        if item[1] - EPS <= now:
            del self._notice[key]
            return None
        return item[0]


@dataclass
class _Down:
    t: float
    token: object
    held: bool = False
    consumed: bool = False  # waehrend des Drueckens gedreht: kein Halten, kein Wechsel


class KnobPress:
    """Druecken eines Reglers mit Ebenen. Die Engine reicht herein:

    * ``hold(ref)``: Halten erreicht (noch gedrueckt) – ``press`` der Ebene druecken,
    * ``hold_tap(ref)``: ohne ``call_later`` lange gedrueckt – ``press`` einmal ausloesen,
    * ``cycle(ref)``: kurz gedrueckt – naechste Ebene,
    * ``release(ref)``: Loslassen (gehaltenes ``hold_key`` loesen; auch fuer Regler ohne
      Ebenen, deren Druecken die Engine sofort ausfuehrt),
    * ``hold_ms()``: aktuelle Schwelle (``settings``, wie bei den Tasten-Gesten)."""

    def __init__(self, *, monotonic: Callable[[], float],
                 call_later: Callable[[float, Callable[[], None]], None] | None,
                 hold_ms: Callable[[], int], hold: Callable[[ControlRef], None],
                 hold_tap: Callable[[ControlRef], None], cycle: Callable[[ControlRef], None],
                 release: Callable[[ControlRef], None], guard: Callable[..., None]) -> None:
        self._mono = monotonic
        self._call_later = call_later
        self._hold_ms = hold_ms
        self._hold = hold
        self._hold_tap = hold_tap
        self._cycle = cycle
        self._release = release
        self._guard = guard
        self._down: dict[ControlRef, _Down] = {}

    def down(self, ref: ControlRef) -> None:
        d = self._down[ref] = _Down(self._mono(), object())
        if self._call_later is not None:
            token = d.token
            self._call_later(self._hold_ms() / 1000,
                             lambda: self._guard(self._due, ref, token))

    def _due(self, ref: ControlRef, token: object) -> None:
        d = self._down.get(ref)
        if d is None or d.token is not token or d.held or d.consumed:
            return
        d.held = True
        self._hold(ref)

    def up(self, ref: ControlRef) -> None:
        d = self._down.pop(ref, None)
        if d is None or d.held or d.consumed:
            self._release(ref)
        elif self._call_later is None and \
                self._mono() - d.t >= self._hold_ms() / 1000 - EPS:
            self._hold_tap(ref)  # ohne Zeitgeber entscheidet die Druckdauer
        else:
            self._cycle(ref)

    def turned(self, ref: ControlRef) -> None:
        """Gedrueckt gedreht: das Drehen gilt, das Druecken loest weder Halten noch
        Ebenenwechsel aus."""
        d = self._down.get(ref)
        if d is not None:
            d.consumed = True

    def clear(self) -> None:
        """Angefangene Druecke vergessen (Ansichtswechsel, R24); geplante Rueckrufe laufen
        ins Leere, das Loslassen loest nur noch Gehaltenes."""
        self._down.clear()


# --- Rad-Tippen -------------------------------------------------------------------------

@dataclass
class _WheelTouch:
    x: int
    y: int
    t: float
    view: int
    moved: int = 0
    multi: bool = False  # ein anderer Finger lag waehrenddessen auf dem Rad


class WheelTaps:
    """Beruehrungen des Raddisplays je Finger; ``touch`` meldet ein Tippen auf die Mitte."""

    def __init__(self) -> None:
        self._touches: dict[int, _WheelTouch] = {}

    def touch(self, finger: int, x: int, y: int, down: bool, now: float, view: int) -> bool:
        """``True``, wenn dieses Abheben ein Tippen beendet: Aufsetzen naeher als
        ``TAP_RADIUS_PX`` an der Mitte, kuerzer als ``TAP_MAX_S``, weniger als
        ``MOVE_CANCEL_PX`` gezogen, in derselben Ansicht (R25) und ohne weiteren Finger.
        Beruehrungen aelter als ``TOUCH_STALE_S`` (Abheben verloren) zaehlen nicht mehr."""
        self._touches = {f: t for f, t in self._touches.items()
                         if now - t.t < TOUCH_STALE_S}
        t = self._touches.get(finger)
        if t is not None:
            t.moved = max(t.moved, abs(x - t.x), abs(y - t.y))
        if down:
            if t is None:  # "an" kommt beim Ziehen wiederholt
                multi = bool(self._touches)
                for other in self._touches.values():
                    other.multi = True
                self._touches[finger] = _WheelTouch(x, y, now, view, multi=multi)
            return False
        self._touches.pop(finger, None)
        return t is not None and not t.multi and t.view == view and t.moved < MOVE_CANCEL_PX \
            and now - t.t < TAP_MAX_S - EPS \
            and math.hypot(t.x - WHEEL_CENTER, t.y - WHEEL_CENTER) < TAP_RADIUS_PX

    def clear(self) -> None:
        self._touches.clear()

