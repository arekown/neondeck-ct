"""Zustaende von Tasten (``Assignment.states`` + ``state_source``), ohne Qt.

Quellen (``state_source["type"]``):

* ``manual``: Druecken fuehrt die Aktion des aktuellen Zustands aus (hat er keine: die
  Grundaktion) und schaltet danach zyklisch weiter. Beginnt bei Zustand 0.
* ``external`` (und ohne Quelle): nur ``state.set`` (API/CLI) setzt den Zustand; bis dahin
  gilt das Grundbild.
* ``mute`` / ``mic_mute``: Standard-Audioausgang/-eingang stumm (``desktop.audio_state``).
* ``media``: irgendein MPRIS-Player spielt (``desktop.mpris``).
* ``app_running``: ein Fenster der App ``state_source["app"]`` ist offen (KWin-Fensterliste).

Bei den Ja/Nein-Quellen ist Zustand 0 = nein (nicht stumm, spielt nicht, laeuft nicht) und
Zustand 1 = ja; solange der Wert unbekannt ist (``None``), gilt das Grundbild.

Gemerkte Zustaende (manuell/extern) haengen am Bedienelement *auf seiner Seite*: Touch-Tasten
an (Profil, Arbeitsbereich, Seiten-ID, Feld), runde/eckige Tasten (profilweit belegt) an
(Profil, Art, Nummer). So bleibt der Zustand ueber Seiten-, Arbeitsbereichs- und
Profilwechsel erhalten, und dasselbe Feld auf einer anderen Seite hat seinen eigenen.
Alles nur im Speicher, bis zum Neustart.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..core.i18n import tr
from ..core.windows import WindowInfo
from ..device.layout import ControlKind
from ..profile.model import Assignment

FLAG_SOURCES = ("mute", "mic_mute", "media")
SOURCE_TYPES = ("manual", "external", *FLAG_SOURCES, "app_running")

StateKey = tuple


def state_key(profile_id: str, kind: str, index: int, workspace_id: str = "",
              page_id: str = "") -> StateKey:
    """Schluessel eines Bedienelements (siehe Moduldoku)."""
    if kind == ControlKind.TOUCH:
        return (profile_id, workspace_id, page_id, kind, index)
    return (profile_id, kind, index)


def source_type(a: Assignment) -> str | None:
    src = a.state_source
    t = src.get("type") if isinstance(src, dict) else None
    return t if t in SOURCE_TYPES else None


class StateStore:
    """Gemerkte Zustaende und die Werte der Systemquellen."""

    def __init__(self) -> None:
        self._index: dict[StateKey, int] = {}
        self._flags: dict[str, bool | None] = {s: None for s in FLAG_SOURCES}
        self._windows: list[WindowInfo] = []

    # --- Quellen ------------------------------------------------------------------

    def set_flag(self, source: str, value: bool | None) -> bool:
        """Wert einer Ja/Nein-Quelle setzen; ``True``, wenn er sich geaendert hat."""
        if source not in self._flags:
            raise ValueError(tr("Unbekannte Zustandsquelle {source!r}", source=source))
        value = None if value is None else bool(value)
        if self._flags[source] is value:
            return False
        self._flags[source] = value
        return True

    def flag(self, source: str) -> bool | None:
        return self._flags.get(source)

    def set_windows(self, windows: Iterable[WindowInfo]) -> None:
        self._windows = list(windows)

    # --- Zustaende ----------------------------------------------------------------

    def set(self, key: StateKey, n: int) -> None:
        """Zustand von Hand setzen (``state.set``); ungueltige Nummern zeigen das Grundbild."""
        self._index[key] = n

    def current(self, a: Assignment, key: StateKey) -> int | None:
        """Aktueller Zustand (Index in ``a.states``) oder ``None`` = Grundbild/-aktion."""
        if not a.states:
            return None
        src = source_type(a)
        if src in FLAG_SOURCES:
            value = self._flags[src]
            n = None if value is None else int(value)
        elif src == "app_running":
            app = (a.state_source or {}).get("app")
            n = int(isinstance(app, str) and any(w.matches(app) for w in self._windows))
        elif src == "manual":
            n = self._index.get(key, 0)
        else:  # external oder keine Quelle
            n = self._index.get(key)
        if n is None or isinstance(n, bool) or not 0 <= n < len(a.states):
            return None
        return n

    def tap_action(self, a: Assignment, key: StateKey) -> dict:
        """Aktion beim (einfachen) Tippen: die des aktuellen Zustands, sonst die Grundaktion."""
        n = self.current(a, key)
        if n is not None:
            action = a.states[n].action
            if isinstance(action, dict) and action.get("type"):
                return action
        return a.action or {}

    def after_tap(self, a: Assignment, key: StateKey) -> None:
        """Nach dem Tippen: Quelle ``manual`` schaltet zyklisch weiter."""
        if source_type(a) != "manual" or not a.states:
            return
        n = self.current(a, key)  # ungueltig gesetzt (Grundbild): weiter mit Zustand 0
        self._index[key] = 0 if n is None else (n + 1) % len(a.states)
