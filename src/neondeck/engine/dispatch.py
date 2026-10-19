"""Aktionen ausloesen und ihre Ergebnisse anzeigen (ohne Qt).

Navigation (``kinds.NAV_TYPES``) laeuft direkt im Engine-Thread, alles andere im Executor (je
Bedienelement seriell, nicht blockierend). Ergebnisse kommen ueber ``post`` zurueck: Fehler
als roter Rand und Statusmeldung, Werte (z. B. „42 %“) in der Leiste bzw. im Rad-Bogen.
Drehungen sammelt der ``Spinner`` (siehe ``encoders``).
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from ..actions.base import ActionContext, Result, execute, registry
from ..core.i18n import N_, tr
from ..device.layout import ControlKind, ControlRef
from .controls import PRESS, ControlResolver
from .encoders import Spinner
from .kinds import LIVE_TYPES, NAV_TYPES, action_type
from .navigation_state import FolderLevel
from .ports import EngineHooks, EnginePorts, Redraw
from .state import FLASH_S, VALUE_S, EngineState

log = logging.getLogger(__name__)

KNOB, WHEEL = ControlKind.KNOB, ControlKind.WHEEL
ROTATE = "rotate"  # Merkzeichen einer Drehung (``Spinner.done``)
ERROR_TEXT = N_("Fehler: {message}")
FAILED_TEXT = N_("Aktion fehlgeschlagen")


@dataclass(frozen=True)
class _Stale:
    """Merkzeichen eines Regler-Ergebnisses, dessen Regler inzwischen anders belegt ist
    (Mixer betreten/verlassen): Fehler zaehlen, der Wert erscheint nicht mehr in der Leiste."""
    tag: object


class ActionDispatcher:
    """Reicht Aktionen an den Executor bzw. die Navigation weiter und wertet die Ergebnisse
    aus. ``call(name, params)`` ist die Navigation der Engine (``Engine.call``)."""

    def __init__(self, ports: EnginePorts, hooks: EngineHooks,
                 state: EngineState, controls: ControlResolver, *,
                 call: Callable[[str, dict], None], redraw: Redraw,
                 after_action: Callable[[], None], guard: Callable[..., None]) -> None:
        post = ports.post
        # Aus Worker-Threads: nur ueber post in den Engine-Thread, dort abgesichert ausfuehren.
        self._executor = ports.executor_factory(
            lambda name, params: post(lambda: guard(call, name, params)),
            lambda ref, res: post(lambda: guard(self._on_result, ref, res)))
        self._nav_ctx = ActionContext(engine_call=call)
        self._call = call
        self._clock = ports.clock
        self._hooks = hooks
        self._state = state
        self._controls = controls
        self._redraw = redraw
        self._after_action = after_action  # Mixer: Werte neu lesen
        self.spinner = Spinner(call_later=ports.call_later, turn=controls.turn,
                               submit=self._submit_rotation)
        self._inflight: dict[ControlRef, deque[object]] = {}
        self._held: dict[ControlRef, dict] = {}

    # --- Ausloesen -----------------------------------------------------------------------

    def press(self, ref: ControlRef, action: dict | None) -> None:
        """Wie ein Tastendruck: ``hold_key`` u. ae. bleiben bis ``release`` gedrueckt."""
        t = action_type(action)
        if not t or t in LIVE_TYPES:
            return
        if t in NAV_TYPES:
            self._navigate(action)
            return
        at = registry().get(t)
        if at and at.on_release:
            self._held[ref] = action
        self._submit(ref, action, tag=self._controls.exit_tag(ref))

    def release(self, ref: ControlRef) -> None:
        held = self._held.pop(ref, None)
        if held is not None:
            self._submit(ref, held, pressed=False)

    def trigger(self, ref: ControlRef, action: dict | None, *, steps: int = 0) -> None:
        """Aktion einmal ausloesen wie ein kurzes Antippen (auch „Testen“ im
        Einstellungsfenster): Navigation direkt, alles andere im Executor (nicht blockierend)."""
        t = action_type(action)
        if not t or t in LIVE_TYPES:
            return
        if t in NAV_TYPES:
            self._navigate(action)
            return
        self._submit(ref, action, steps=steps, tag=self._controls.exit_tag(ref))
        at = registry().get(t)
        if at and at.on_release:
            self._submit(ref, action, pressed=False)

    def rotate(self, ref: ControlRef, delta: int) -> None:
        self.spinner.rotate(ref, delta)

    def drop_rotation(self, ref: ControlRef | None = None) -> None:
        """Gesammelte Drehungen (aller oder eines Reglers) gehoeren zur alten Belegung."""
        self.spinner.drop_pending(ref)

    def drop_knob_spins(self, knobs: list[int]) -> None:
        """Mixer-Liste verschoben: Gesammeltes dieser Regler gehoerte zum vorigen Stream."""
        for i in knobs:
            self.spinner.drop_pending(ControlRef(KNOB, i))

    def release_held(self) -> None:
        for ref, action in list(self._held.items()):
            self._submit(ref, action, pressed=False)
        self._held.clear()

    def knobs_reassigned(self) -> None:
        """Regler wechseln ihre Belegung (Mixer): Leistenwerte verfallen, noch laufende
        Ergebnisse der alten Belegung zeigen keinen Wert mehr."""
        self._state.feedback.values.clear()
        for ref, tags in self._inflight.items():
            if ref.kind == KNOB:
                marked = [t if isinstance(t, _Stale) else _Stale(t) for t in tags]
                tags.clear()
                tags.extend(marked)

    def shutdown(self) -> None:
        self._executor.shutdown()

    def _navigate(self, action: dict) -> None:
        """Navigation laeuft direkt im Engine-Thread (reiner Zustandswechsel)."""
        res = execute(action, self._nav_ctx)
        if not res.ok:
            log.warning("Navigation %s fehlgeschlagen: %s", action.get("type"), res.message)

    def _submit_rotation(self, ref: ControlRef, action: dict, steps: int) -> bool:
        return self._submit(ref, action, steps=steps, tag=ROTATE)

    def _submit(self, ref: ControlRef, action: dict, *, steps: int = 0, pressed: bool = True,
                tag: object = PRESS) -> bool:
        # Der Executor fuehrt je ControlRef seriell aus, Ergebnisse kommen in dieser Reihenfolge.
        tags = self._inflight.setdefault(ref, deque())
        tags.append(tag)
        try:
            self._executor.submit(ref, action, steps=steps, pressed=pressed)
        except Exception:
            log.exception("Aktion %s nicht eingereiht", action.get("type"))
            tags.pop()
            if not tags:
                del self._inflight[ref]
            return False
        return True

    # --- Ergebnisse ----------------------------------------------------------------------

    def _pop_tag(self, ref: ControlRef) -> object:
        tags = self._inflight.get(ref)
        tag = tags.popleft() if tags else PRESS
        if tags is not None and not tags:
            del self._inflight[ref]
        return tag

    def _on_result(self, ref: ControlRef, res: Result) -> None:
        tag = self._pop_tag(ref)
        stale = isinstance(tag, _Stale)
        if stale:
            tag = tag.tag
        now = self._clock()
        if ref.kind == ControlKind.STRIP:  # eigene Tipp-Aktion der Leiste: Fehler/Wert dort
            ref = ControlRef(KNOB, ref.index)
        if not res.ok:
            self._show_error(ref, res, now)
        elif (res.message or res.value is not None) and ref.kind in (KNOB, WHEEL) \
                and not stale:
            self._show_value(ref, res, now)
        if tag == ROTATE:
            self.spinner.done(ref)
        elif isinstance(tag, FolderLevel) and res.ok and self._controls.is_folder_top(tag):
            self._call("folder_back", {})  # Auto-Exit: nur, wenn ihre Ebene die innerste ist
        self._after_action()
        self._redraw.now()

    def _show_error(self, ref: ControlRef, res: Result, now: float) -> None:
        if ref.kind in (ControlKind.TOUCH, KNOB):
            self._state.feedback.flashes[ref] = now + FLASH_S
            self._redraw.later(FLASH_S)
        if self._hooks.on_status:
            self._hooks.on_status(tr(ERROR_TEXT, message=res.message or tr(FAILED_TEXT)))

    def _show_value(self, ref: ControlRef, res: Result, now: float) -> None:
        if ref.kind == KNOB:
            self._state.feedback.values[ref.index] = (res.message, res.value, now + VALUE_S)
            self._redraw.later(VALUE_S)
        else:
            self._state.feedback.note_wheel(res)
        if self._hooks.on_value:
            self._hooks.on_value(ref, res.message)
