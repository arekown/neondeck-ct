"""Welche Belegung ein Bedienelement in der aktuellen Ansicht hat (ohne Qt).

``ControlResolver`` beantwortet alle Fragen „was liegt hier?“: angezeigte Seite (ein offener
dynamischer Ordner liegt ueber ``page_index``), Felder samt Sticky-Kacheln und „Zurück“,
Regler (Mixer: je Anwendung) mit ihrer aktiven Ebene, Drehbelegung, Zustandsschluessel und
die Stoppuhren der Felder. Er aendert nur die Ebenen-Auswahl und die Stoppuhren.
"""
from __future__ import annotations

from ..actions.base import Trigger
from ..device.layout import ROUND_FIRST, SQUARE_CODES, ControlKind, ControlRef
from ..profile.edit import sticky_at
from ..profile.model import Assignment, Encoder, EncoderLayer, TouchPage
from .dynamic_folders import DynamicFolders, VirtualPage
from .encoders import Layers, Turn
from .kinds import typed
from .navigation_state import FolderLevel, FolderStack, page_at, shown_assignment
from .state import EngineState
from .states import StateKey, StateStore, state_key
from .stopwatch import Stopwatch

KNOB, WHEEL, STRIP, TOUCH = ControlKind.KNOB, ControlKind.WHEEL, ControlKind.STRIP, ControlKind.TOUCH
STICKY = "sticky"  # Stoppuhr einer Sticky-Kachel: auf allen Seiten dieselbe
PRESS = "press"    # Merkzeichen einer Aktion ohne Auto-Exit (siehe ``exit_tag``)


class ControlResolver:
    """Belegungen der aktuellen Ansicht aus ``state``, offenem Ordner und Ebenen."""

    def __init__(self, state: EngineState, dynamic: DynamicFolders, folders: FolderStack,
                 layers: Layers, states: StateStore) -> None:
        self._state = state
        self.dynamic = dynamic
        self.folders = folders
        self.layers = layers
        self.states = states
        self._stopwatches: dict[tuple, Stopwatch] = {}

    # --- Seite ---------------------------------------------------------------------------

    def dynamic_page(self) -> VirtualPage | None:
        return self.dynamic.page()

    def mixer(self) -> VirtualPage | None:
        """Offener dynamischer Ordner mit eigenen Reglern (Mixer), sonst ``None``."""
        dyn = self.dynamic.page()
        return dyn if dyn is not None and dyn.encoders is not None else None

    def page(self) -> TouchPage | None:
        """Angezeigte Seite: ein offener dynamischer Ordner liegt ueber ``page_index``."""
        dyn = self.dynamic.page()
        return dyn.page if dyn is not None else page_at(self._state.workspace,
                                                        self._state.page_index)

    def in_folder(self) -> bool:
        page = self.page()
        return page is not None and page.folder

    def base_index(self) -> int:
        """Die normale Seite der Ansicht: im Ordner die, von der er geoeffnet wurde."""
        return self.folders.base_index(self._state.workspace, self._state.page_index)

    # --- Regler und Rad ------------------------------------------------------------------

    def encoder(self, index: int) -> Encoder:
        mixer = self.mixer()
        if mixer is not None:  # Mixer: Regler je Anwendung
            return mixer.encoders[index] if index < len(mixer.encoders) else Encoder()
        ws = self._state.workspace
        return ws.encoders[index] if ws and index < len(ws.encoders) else Encoder()

    def layer_key(self, index: int) -> tuple:
        return (self._state.profile.id, self._state.workspace_id, index)

    def layer(self, index: int) -> EncoderLayer | None:
        """Aktive Ebene des Reglers (``None`` ohne Ebenen)."""
        return self.layers.active(self.layer_key(index), self.encoder(index))

    def layer_press(self, ref: ControlRef) -> dict | None:
        layer = self.layer(ref.index)
        return layer.press if layer else None

    def turn(self, ref: ControlRef) -> Turn | None:
        """Drehbelegung von Rad oder Regler (mit Ebenen: die der aktiven Ebene)."""
        if ref.kind == WHEEL:
            ws = self._state.workspace
            if ws is None:
                return None
            w = ws.wheel
            turn = Turn(w.rotate, w.left, w.right, w.invert, w.factor)
        else:
            enc = self.encoder(ref.index)
            src = self.layer(ref.index) or enc
            turn = Turn(src.rotate, src.left, src.right, enc.invert, enc.factor)
        return turn if turn.assigned else None

    def strip_tap(self, index: int) -> dict | None:
        """Eigene Tipp-Aktion des Leistenabschnitts ``index`` (``Encoder.tap``), sonst
        ``None`` (dann wirkt Tippen wie Regler-Druck)."""
        tap = self.encoder(index).tap
        return tap if typed(tap) else None

    def wheel_tap(self) -> dict | None:
        ws = self._state.workspace
        return ws.wheel.tap if ws else None

    # --- Tasten --------------------------------------------------------------------------

    def tile(self, index: int) -> Assignment | None:
        """Belegung von Feld ``index``: im Ordner ist Feld 0 „Zurück“, auf normalen Seiten
        ersetzen Sticky-Kacheln des Arbeitsbereichs das Feld."""
        return shown_assignment(self._state.workspace, self.page(), index)

    def sticky(self, index: int) -> Assignment | None:
        """Sticky-Kachel auf Feld ``index`` (nur auf normalen Seiten)."""
        return sticky_at(self._state.workspace, self.page(), index)

    def assignment(self, ref: ControlRef) -> Assignment | None:
        profile = self._state.profile
        if ref.kind == TOUCH:
            return self.tile(ref.index)
        if ref.kind == ControlKind.ROUND:
            return profile.round.get(ROUND_FIRST + ref.index)
        if ref.kind == ControlKind.SQUARE and 0 <= ref.index < len(SQUARE_CODES):
            return profile.square.get(SQUARE_CODES[ref.index])
        return None

    def state_key(self, ref: ControlRef) -> StateKey:
        """Schluessel des Bedienelements in der aktuellen Ansicht (siehe ``states``)."""
        st = self._state
        if ref.kind == TOUCH:
            if self.sticky(ref.index) is not None:  # auf allen Seiten dieselbe Kachel
                return state_key(st.profile.id, ref.kind, ref.index, st.workspace_id, None)
            page = self.page()
            return state_key(st.profile.id, ref.kind, ref.index, st.workspace_id,
                             page.id if page else "")
        return state_key(st.profile.id, ref.kind, ref.index)

    def state_of(self, ref: ControlRef) -> int | None:
        """Aktueller Zustand der Taste in der aktuellen Ansicht (``None`` = Grundbild)."""
        a = self.assignment(ref)
        return self.states.current(a, self.state_key(ref)) if a is not None else None

    def action_for(self, ref: ControlRef, which: Trigger = Trigger.TAP) -> dict | None:
        """Belegte Aktion eines Bedienelements in der aktuellen Ansicht (``tap``, ``double``,
        ``hold`` oder ``rotate``); ``None``, wenn nichts belegt ist. Regler mit Ebenen:
        ``hold`` = ``press`` der aktiven Ebene, ``tap`` wechselt nur die Ebene (``None``)."""
        if ref.kind == STRIP:  # Leisten-Beruehrung: eigene Tipp-Aktion oder Regler-Druck
            tap = self.strip_tap(ref.index)
            if tap is not None:
                return tap if which == Trigger.TAP else None
            ref = ControlRef(KNOB, ref.index)
        if which == Trigger.ROTATE:
            turn = self.turn(ref) if ref.kind in (KNOB, WHEEL) else None
            action = turn.first if turn else None
        elif ref.kind == KNOB:
            action = self._knob_action(ref.index, which)
        elif ref.kind == WHEEL:
            action = self.wheel_tap() if which == Trigger.TAP else None
        else:
            action = self._button_action(ref, which)
        return action if typed(action) else None

    def _knob_action(self, index: int, which: Trigger) -> dict | None:
        layer = self.layer(index)
        if layer is not None:
            return layer.press if which == Trigger.HOLD else None
        return self.encoder(index).press if which == Trigger.TAP else None

    def _button_action(self, ref: ControlRef, which: Trigger) -> dict | None:
        a = self.assignment(ref)
        if a is None:
            return None
        if which == Trigger.TAP:
            return self.states.tap_action(a, self.state_key(ref))
        return {Trigger.DOUBLE: a.double, Trigger.HOLD: a.hold}.get(which)

    # --- Ordner und Stoppuhren -----------------------------------------------------------

    def exit_tag(self, ref: ControlRef) -> object:
        """Aktion einer Kachel im Ordner mit Auto-Exit: die Ebene als Merkzeichen, damit ihr
        erfolgreiches Ergebnis genau diese Ebene verlaesst (sonst ``PRESS``)."""
        top = self.folders.top
        page = self.page()
        if ref.kind == TOUCH and top is not None and top.auto_exit and page is not None \
                and page.id == top.page:
            return top
        return PRESS

    def is_folder_top(self, level: FolderLevel) -> bool:
        return self.folders.top is level

    def stopwatch(self, index: int) -> Stopwatch:
        page = STICKY if self.sticky(index) is not None else self._state.page_index
        return self._stopwatches.setdefault((self._state.workspace_id, page, index),
                                            Stopwatch())

    def clear_stopwatches(self) -> None:
        self._stopwatches.clear()
