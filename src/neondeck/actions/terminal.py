"""Aktion „Konsole-Layout“: mehrere Konsole-Fenster mit Titel, Befehl(en) und Platz.

Je Fenster eine Konsole mit Layout- bzw. Register-Datei (``konsole``); die Fenster starten
nacheinander: jedes wartet, bis KWin es gemeldet und platziert hat (``core.placement``) – so
landet jedes Fenster sicher auf seinem Platz. Danach kommen die Titel ueber Konsoles D-Bus.

Gespeichert als ``{"type": "terminal_layout", "screen": "DP-3", "windows": [...]}`` (Format
der Fenster: ``terminal_windows``; der Editor zeigt sie als Text).
"""
from __future__ import annotations

import logging

from ..core.i18n import N_, tr
from .base import ActionContext, Param, Result, register
from .konsole import KonsoleBus, window_argv, window_file
from .placing import SCREEN_PARAM, pid_of, spawn_placed
from .terminal_windows import clean_windows

log = logging.getLogger(__name__)

KONSOLE_APP = "org.kde.konsole"
WINDOW_WAIT_S = 10.0   # so lange auf das Fenster warten, bevor das naechste startet

def _name_tabs(bus: KonsoleBus, pid: int, win: dict) -> None:
    """Titel des letzten Registers (laeuft ueber ``-e``, steht nicht in der Datei) setzen und das
    erste Register nach vorn holen."""
    sessions = sorted(bus.sessions(), key=int)
    count = len(win["tabs"])
    if len(sessions) < count:
        log.warning("Konsole %s meldet %d von %d Registern", pid, len(sessions), count)
        return
    title = win["tabs"][-1]["title"] or win["title"]
    if title:
        bus.set_title(sessions[count - 1:count], title)
    bus.show(sessions[0])


def _name_views(bus: KonsoleBus, pid: int, win: dict) -> None:
    """Konsole hat die Layoutdatei gelesen, sobald seine Ansichten auf D-Bus stehen."""
    sessions = bus.sessions()
    if win["title"] and sessions:
        bus.set_title(sessions, win["title"])
    elif win["title"]:
        log.warning("Titel %r nicht gesetzt: Konsole %s meldet keine Ansichten",
                    win["title"], pid)


def open_window(ctx: ActionContext, win: dict, screen: str = "") -> Result:
    """Ein Konsole-Fenster starten, auf seinen Platz warten und den Titel setzen."""
    path = window_file(win)
    try:
        try:
            proc, ticket = spawn_placed(ctx, window_argv(win, path), KONSOLE_APP,
                                        win.get("screen") or screen, win["place"])
        except FileNotFoundError:
            return Result(False, tr("Programm nicht gefunden: {program}", program="konsole"))
        pid = pid_of(proc)
        if ticket is not None and not ticket.wait(WINDOW_WAIT_S):
            log.warning("Konsole-Fenster %r kam nicht in %s s", win["title"], WINDOW_WAIT_S)
        if win.get("tabs"):
            if pid:
                _name_tabs(KonsoleBus(ctx, pid), pid, win)
        elif pid:
            _name_views(KonsoleBus(ctx, pid), pid, win)
        elif win["title"]:
            log.warning("Titel %r nicht gesetzt: Konsole %s meldet keine Ansichten",
                        win["title"], pid)
    finally:
        path.unlink(missing_ok=True)
    return Result(True)


@register("terminal_layout", label=N_("Konsole-Layout"), category="apps", params=[
    SCREEN_PARAM, Param("windows", N_("Fenster"), "terminals")])
def terminal_layout(action, ctx, **_):
    windows = clean_windows(action.get("windows"))
    if not windows:
        return Result(False, tr("Keine Fenster angegeben"))
    for win in windows:
        res = open_window(ctx, win, str(action.get("screen") or ""))
        if not res.ok:
            return res
    return Result(True)
