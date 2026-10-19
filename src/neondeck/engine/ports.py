"""Anschluesse der Engine nach aussen (ohne Qt): Geraet, Executor, Uhren und Zeitgeber
(``EnginePorts``), Rueckmeldungen an den Dienst (``EngineHooks``), Startwerte aus den
Einstellungen (``EngineOptions``) und die Schnittstelle eines Geraete-Looks (``Look``).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import KW_ONLY, dataclass
from typing import Protocol

from PIL import Image

from ..actions.base import Result
from ..core.assets import resolve
from ..core.sysload import SystemLoad
from ..device.layout import ControlRef, Display
from ..render import look as looks
from ..render.icons import load_icon
from ..render.images import TileSpec
from .dynamic_folders import DynamicSources
from .gestures import DOUBLE_MS, HOLD_MS

Clock = Callable[[], float]
CallLater = Callable[[float, Callable[[], None]], None]
PostFn = Callable[[Callable[[], None]], None]
DrawFn = Callable[[Display, bytes], None]          # ein Display mit RGB565-Bytes beschreiben
LedFn = Callable[[dict[int, tuple]], None]         # Farben der runden Tasten
IconLoader = Callable[[str, int], Image.Image | None]
Paint = Callable[[], Image.Image]                  # Bild erst zeichnen, wenn es gebraucht wird
TileSpecs = list[tuple[TileSpec | None, str | None]]  # (Kachel, Symbol-Ref) je Feld
RenderTiles = Callable[[TileSpecs, tuple], list[Image.Image | None]]


class Executor(Protocol):
    """Fuehrt Aktionen je Bedienelement der Reihe nach aus (``actions.base.Executor``)."""

    def submit(self, ref: ControlRef, action: dict, steps: int = 0,
               pressed: bool = True) -> None: ...

    def shutdown(self) -> None: ...


# (engine_call, on_result) -> Executor; beide Rueckrufe kommen aus Worker-Threads
ExecutorFactory = Callable[[Callable[[str, dict], None], Callable[[ControlRef, Result], None]],
                           Executor]


def default_icon_loader(ref: str, size: int) -> Image.Image | None:
    return load_icon(ref, size, resolve)


@dataclass(frozen=True)
class EnginePorts:
    """Was die Engine braucht: zeichnen, LEDs setzen, Aktionen ausfuehren, Symbole laden; dazu
    ``post`` (Rueckruf in den Engine-Thread), Wanduhr ``clock``, ``monotonic`` (Schlafuhr und
    Gesten, unabhaengig von Spruengen der Wanduhr) und ``call_later`` (ohne: keine Zeitgeber)."""
    draw: DrawFn
    leds: LedFn
    executor_factory: ExecutorFactory
    icon_loader: IconLoader | None = None
    _: KW_ONLY
    post: PostFn
    clock: Clock = time.time
    monotonic: Clock = time.monotonic
    call_later: CallLater | None = None
    dynamic_sources: DynamicSources | None = None
    system_load: SystemLoad | None = None


@dataclass
class EngineHooks:
    """Rueckmeldungen an den Dienst (alle optional, zur Laufzeit austauschbar)."""
    on_open_config: Callable[[], None] | None = None
    on_status: Callable[[str], None] | None = None           # Fehlermeldung einer Aktion
    on_profile: Callable[[str], None] | None = None          # Aktion „Profil wechseln“
    on_view: Callable[[], None] | None = None                # Arbeitsbereich/Seite/Profil
    on_value: Callable[[ControlRef, str], None] | None = None  # Wert eines Reglers/Rads
    on_dark: Callable[[bool], None] | None = None            # hell/dunkel gewechselt
    on_saver: Callable[[bool], None] | None = None           # Bildschirmschoner an/aus
    on_animate: Callable[[bool], None] | None = None         # Takt des Looks an/aus


@dataclass(frozen=True)
class EngineOptions:
    """Startwerte aus den Einstellungen; zur Laufzeit gibt der Dienst Aenderungen ueber
    ``Engine.set_display_sleep``/``set_saver``/``set_key_timing`` weiter."""
    views: dict | None = None    # ``settings.last_pages``
    display_sleep_min: int = 0   # 0 = aus
    double_ms: int = DOUBLE_MS
    hold_ms: int = HOLD_MS
    saver_min: int = 0           # 0 = aus
    saver_name: str = "cockpit"
    saver_options: dict | None = None  # Diashow: ``folder``, ``slide_s``
    device_look: str = looks.CLASSIC


@dataclass(frozen=True)
class Redraw:
    """Neu zeichnen lassen: sofort (``now``) oder nach ``delay`` Sekunden (ohne
    ``call_later``: erst beim naechsten Anlass)."""
    now: Callable[[], None]
    call_later: CallLater | None

    def later(self, delay: float) -> None:
        if self.call_later is not None:
            self.call_later(delay, self.now)


class Look(Protocol):
    """Geraete-Look als Strategie: liefert je Display einen Vergleichsschluessel und das
    Zeichnen dazu (nur bei neuem Schluessel gezeichnet). ``frame`` ist die Bildnummer."""
    name: str
    animated: bool

    def center(self, specs: TileSpecs, dot: int, dots: int, frame: int,
               render: RenderTiles) -> tuple[object, Paint]: ...

    def strip(self, sections: list[tuple[str, str | None, float | None]], flashing: tuple,
              pressed: tuple, frame: int, edge: str) -> tuple[object, Paint]: ...

    def system_strip(self, values: tuple, flashing: tuple, frame: int,
                     edge: str) -> tuple[object, Paint]: ...

    def wheel(self, key: tuple, base: Paint, frame: int) -> tuple[object, Paint]: ...

    def leds(self, colors: dict[int, tuple], active: set[int],
             frame: int) -> dict[int, tuple]: ...
