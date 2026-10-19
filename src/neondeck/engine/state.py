"""Gemeinsamer Zustand der Engine-Teile (ohne Qt): Profil, Ansicht, hell/dunkel und die
Rueckmeldungen der aktuellen Ansicht.

Die Teile (``view``, ``controls``, ``input``, ``dispatch``, ``painter``, ``power``) lesen und
schreiben nur hier und greifen sich nicht gegenseitig in die Attribute.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..actions.base import Result
from ..core.values import EPS
from ..device.layout import ControlKind, ControlRef
from ..profile.model import Profile, Workspace

FLASH_S = 0.6   # roter Rand nach einem Fehler
VALUE_S = 2.0   # Wert (z. B. "42 %") bzw. Ebenen-Hinweis in der Leiste


@dataclass
class Feedback:
    """Was die Anzeige ueber die Bedienung zeigt, solange die Ansicht bleibt: roter Rand nach
    Fehlern (``flashes``: bis wann), Leistenwerte je Regler (``values``: Text, Prozent, bis
    wann), der Rad-Bogen und gedrueckte Felder (``highlight``)."""
    flashes: dict[ControlRef, float] = field(default_factory=dict)
    values: dict[int, tuple[str, float | None, float]] = field(default_factory=dict)
    wheel_value: float | None = None  # letzter Prozentwert der Rad-Aktion
    wheel_muted: bool = False         # letzte Meldung war „stumm“
    highlight: set[int] = field(default_factory=set)

    def clear(self) -> None:
        """Alles vergessen (anderer Arbeitsbereich, anderes Profil)."""
        self.flashes.clear()
        self.values.clear()
        self.wheel_value, self.wheel_muted = None, False
        self.highlight.clear()

    def leave_page(self) -> None:
        """Andere Seite: Fehlerrand der Felder und gedrueckte Felder verfallen, Regler und
        Rad behalten ihre Werte."""
        self.flashes = {r: u for r, u in self.flashes.items() if r.kind != ControlKind.TOUCH}
        self.highlight.clear()

    def expire(self, now: float) -> None:
        self.flashes = {r: u for r, u in self.flashes.items() if u - EPS > now}
        self.values = {i: v for i, v in self.values.items() if v[2] - EPS > now}

    def note_wheel(self, res: Result) -> None:
        """Rad-Bogen: nur Prozentwerte ersetzen den letzten Wert; „stumm“ behaelt ihn und
        markiert ihn, andere Meldungen (z. B. Programmausgaben) aendern nichts."""
        if res.value is not None:
            self.wheel_value, self.wheel_muted = min(100.0, max(0.0, res.value)), False
        elif res.muted:
            self.wheel_muted = True


@dataclass
class EngineState:
    """Profil und Ansicht (Arbeitsbereich, Seite, Zaehler der Ansichtswechsel), dazu ob das
    Geraet verbunden, gesperrt, im Display-Schlaf oder im Bildschirmschoner ist."""
    profile: Profile
    workspace_id: str = ""
    page_index: int = 0
    view_gen: int = 0          # jeder Ansichtswechsel zaehlt hoch (R25)
    device_connected: bool = True
    locked: bool = False
    asleep: bool = False
    saver_on: bool = False
    feedback: Feedback = field(default_factory=Feedback)

    @property
    def workspace(self) -> Workspace | None:
        return self.find_workspace(self.workspace_id)

    def find_workspace(self, ws_id: object) -> Workspace | None:
        return next((w for w in self.profile.workspaces if w.id == ws_id), None)

    @property
    def dark(self) -> bool:
        """Gesperrt oder im Display-Schlaf: Displays schwarz, LEDs aus."""
        return self.locked or self.asleep

    @property
    def paused(self) -> bool:
        """Dunkel oder getrennt: Hintergrund-Takte (Mixer) fragen nichts ab."""
        return self.dark or not self.device_connected

    @property
    def showing(self) -> bool:
        """Zeigt das Geraet die Ansicht (hell, kein Bildschirmschoner)?"""
        return not self.dark and not self.saver_on
