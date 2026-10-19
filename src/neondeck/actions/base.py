"""Aktions-Grundgeruest: Registry, Ausfuehrungskontext, nicht blockierender Executor."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from typing import Any

from ..core import proc
from ..core.errors import LoupedeckError
from ..core.i18n import N_, tr
from ..core.workers import Worker
from ..device.layout import ControlRef

log = logging.getLogger(__name__)

# gleichzeitig laufende Aktionen (je Bedienelement immer nur eine); lange Aktionen (Warten,
# Konsole-Layout) belegen je einen Platz, Threads sind billig
ACTION_WORKERS = 8


class ActionError(LoupedeckError):
    """Erwarteter Fehler einer Aktion (Text fuer Leiste/Status), z. B. fehlende Tastatur."""


class Trigger(StrEnum):
    """Wie ein Bedienelement ausgeloest wird (API ``trigger``, ``Engine.activate``)."""
    TAP = "tap"
    DOUBLE = "double"
    HOLD = "hold"
    ROTATE = "rotate"


class ParamKind(StrEnum):
    """Art eines Aktionsparameters (Editor waehlt danach das Eingabefeld)."""
    TEXT = "text"
    FILE = "file"
    DIR = "dir"
    BOOL = "bool"
    INT = "int"
    KEYS = "keys"
    CHOICE = "choice"
    STEPS = "steps"
    TERMINALS = "terminals"


@dataclass
class Result:
    """Ergebnis einer Aktion. ``message``: Text fuer Leiste/Status (Anzeige); ``value``: Wert
    in Prozent (0–100) fuer Balken und Rad-Bogen; ``muted``: stumm (Rad-Bogen grau)."""
    ok: bool
    message: str = ""
    value: float | None = None
    muted: bool = False


@dataclass
class Param:
    name: str
    label: str
    kind: ParamKind  # als Text angegeben, beim Anlegen geprueft
    default: Any = None
    choices: list | None = None

    def __post_init__(self) -> None:
        self.kind = ParamKind(self.kind)  # Tippfehler fallen beim Registrieren auf


# Kategorien: Schluessel (Gruppierung) -> Anzeigename; Reihenfolge = Anzeige im Editor
CATEGORIES: dict[str, str] = {"apps": N_("Programme"), "input": N_("Eingabe"),
                              "media": N_("Medien"), "system": N_("System (KDE)"),
                              "navigation": N_("Navigation"), "display": N_("Anzeige"),
                              "macros": N_("Makros")}


@dataclass
class ActionType:
    name: str
    label: str
    category: str  # Schluessel aus ``CATEGORIES``
    params: list[Param]
    kinds: set[str]
    handler: Callable[..., Result | None]
    on_release: bool = False  # auch mit pressed=False aufrufen (z. B. hold_key)


@dataclass
class ActionContext:
    engine_call: Callable[[str, dict], None]
    keyboard: Any | None = None  # virtuelle Tastatur (``Keyboard``)
    run: proc.Runner = proc.run
    popen: Callable[..., Any] = proc.Popen
    # Fenster nach vorn holen: focus(app_id, fenster_id) -> True, wenn eins da war (Dienst:
    # KWin-Fensterwaechter; ohne: Apps werden immer gestartet)
    focus: Callable[[str, str], bool] | None = None
    mouse: Any | None = None  # Mouse (Mausrad ueber uinput)
    # naechstes Fenster einer App platzieren: place(app, bildschirm, platz) -> Ticket | None
    # (Dienst: KWin-Fensterwaechter; ohne: Fenster bleiben, wo KWin sie hinsetzt)
    place: Callable[[str, str, str], Any] | None = None
    # Wiederholen beim aktiven/zuletzt spielenden MPRIS-Player weiterschalten (Dienst)
    media_loop: Callable[[str], None] | None = None
    # Medien direkt beim MPRIS-Player: media_control(methode, player) (Dienst)
    media_control: Callable[[str, str], None] | None = None
    sleep: Callable[[float], None] = time.sleep  # Warten in Aktionen (Tests: sofort)


def keyboard_of(ctx: ActionContext) -> Any:
    """Virtuelle Tastatur des Kontexts; ohne Tastatur ``ActionError``."""
    if ctx.keyboard is None:
        raise ActionError(tr("Keine Tastatur verfügbar"))
    return ctx.keyboard


def mouse_of(ctx: ActionContext) -> Any:
    """Virtuelle Maus des Kontexts; ohne Maus ``ActionError``."""
    if ctx.mouse is None:
        raise ActionError(tr("Keine virtuelle Maus verfügbar"))
    return ctx.mouse


def run_checked(ctx: ActionContext, argv: list[str]) -> Result:
    """Kurzer Aufruf ueber ``ctx.run``; ``Result.message`` = stdout bei Erfolg."""
    ok, text = proc.run_checked(argv, run=ctx.run)
    return Result(ok, text)


def qdbus(ctx: ActionContext, service: str, path: str, method: str, *args: object) -> Result:
    """D-Bus-Aufruf ueber das Werkzeug ``qdbus`` (``run_checked``)."""
    return run_checked(ctx, proc.qdbus_argv(service, path, method, *args))


def spawn_detached(ctx: ActionContext, argv: list[str], workdir: str | None = None):
    """Programm losgeloest ueber ``ctx.popen`` starten (``proc.spawn_detached``)."""
    return proc.spawn_detached(argv, workdir, popen=ctx.popen)


_REGISTRY: dict[str, ActionType] = {}


def register(name: str, *, label: str, category: str, params: list[Param] | None = None,
             kinds: set[str] | None = None, on_release: bool = False):
    def deco(fn):
        _REGISTRY[name] = ActionType(name, label, category, list(params or []),
                                     set(kinds or {"press"}), fn, on_release)
        return fn
    return deco


def registry() -> dict[str, ActionType]:
    return _REGISTRY


def execute(action: dict, ctx: ActionContext, *, steps: int = 0, pressed: bool = True) -> Result:
    t = _REGISTRY.get(action.get("type"))
    if t is None:
        return Result(False, tr("Unbekannte Aktion: {type}", type=action.get("type")))
    if t.kinds == {"press"} and not pressed and not t.on_release:
        return Result(True)
    try:
        res = t.handler(action, ctx, steps=steps, pressed=pressed)
    except ActionError as e:
        return Result(False, str(e))
    except Exception as e:  # nie bis in den Geraete-Thread; Programmfehler mit Traceback
        log.exception("Aktion %s fehlgeschlagen", t.name)
        return Result(False, str(e) or type(e).__name__)
    return res if isinstance(res, Result) else Result(True)


class Executor:
    """Fuehrt Aktionen ausserhalb des aufrufenden Threads aus: je Bedienelement eine Spur
    nacheinander (Druecken und Loslassen ueberholen sich nie), verschiedene parallel."""

    def __init__(self, ctx: ActionContext, on_result: Callable[[ControlRef, Result], None]):
        self.ctx = ctx
        self.on_result = on_result
        self._pool = Worker("action", threads=ACTION_WORKERS)
        self._lock = threading.Lock()
        self._lanes: dict[ControlRef, deque] = {}

    def submit(self, ref: ControlRef, action: dict, steps: int = 0, pressed: bool = True) -> None:
        with self._lock:
            lane = self._lanes.setdefault(ref, deque())
            lane.append((action, steps, pressed))
            if len(lane) > 1:
                return  # ein Worker arbeitet die Spur schon ab
        try:
            self._pool.submit(partial(self._drain, ref))
        except Exception:
            with self._lock:  # kein Worker arbeitet die Spur ab: verwerfen (Pool unbrauchbar)
                self._lanes.pop(ref, None)
            raise

    def _drain(self, ref: ControlRef) -> None:
        while True:
            with self._lock:
                action, steps, pressed = self._lanes[ref][0]
            try:
                self._work(ref, action, steps, pressed)
            except Exception:
                log.exception("Aktion %r auf %s fehlgeschlagen", action, ref)
            finally:
                with self._lock:
                    lane = self._lanes[ref]
                    lane.popleft()
                    done = not lane
                    if done:
                        del self._lanes[ref]
            if done:
                return

    def _work(self, ref, action, steps, pressed):
        res = execute(action, self.ctx, steps=steps, pressed=pressed)
        if not res.ok:
            log.warning("Aktion %s fehlgeschlagen: %s", action.get("type"), res.message)
        try:
            self.on_result(ref, res)
        except Exception:
            log.exception("on_result fehlgeschlagen")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)  # Begonnenes und Eingereihtes laeuft noch zu Ende
