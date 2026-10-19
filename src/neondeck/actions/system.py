"""Aktionen: Programm starten, Ziel oeffnen, Befehl ausfuehren."""
from __future__ import annotations

import logging
import shlex
import threading

from ..core.i18n import N_, tr
from ..core.placement import app_key_of
from ..core.proc import BASH, GIO, KIOCLIENT, KONSOLE, XDG_OPEN
from .base import Param, Result, register, spawn_detached
from .placing import PLACE_PARAM, SCREEN_PARAM, spawn_placed

log = logging.getLogger(__name__)


def _not_found(e: FileNotFoundError, prog: str, workdir: str | None) -> Result:
    """Fehlender Arbeitsordner meldet ``Popen`` ebenfalls als FileNotFoundError (mit dem
    Ordner als ``filename``) – das ist kein fehlendes Programm."""
    if workdir and e.filename == workdir:
        return Result(False, tr("Arbeitsordner nicht gefunden: {workdir}", workdir=workdir))
    return Result(False, tr("Programm nicht gefunden: {program}", program=prog))


@register("run", label=N_("Programm starten"), category="apps", params=[
    Param("command", N_("Befehl"), "text"), Param("workdir", N_("Arbeitsordner"), "dir"),
    SCREEN_PARAM, PLACE_PARAM])
def run(action, ctx, **_):
    argv = shlex.split(action.get("command", ""))
    if not argv:
        return Result(False, tr("Kein Befehl angegeben"))
    try:
        spawn_placed(ctx, argv, app_key_of(argv), action.get("screen"), action.get("place"),
                     action.get("workdir"))
    except FileNotFoundError as e:
        return _not_found(e, argv[0], action.get("workdir"))
    return Result(True)


@register("open", label=N_("Öffnen"), category="apps", params=[
    Param("target", N_("Datei, Ordner, URL oder .desktop-Verknüpfung"), "text")])
def open_target(action, ctx, **_):
    target = action.get("target", "")
    if not target:
        return Result(False, tr("Kein Ziel angegeben"))
    # .desktop-Verknuepfung ausfuehren (Programm starten bzw. Link oeffnen) statt sie im
    # Texteditor zu oeffnen, wie xdg-open es taete
    argvs = ([[KIOCLIENT, "exec", target], [GIO, "launch", target]]
             if target.endswith(".desktop") else []) + [[XDG_OPEN, target]]
    for argv in argvs:
        try:
            spawn_detached(ctx, argv)
            return Result(True)
        except FileNotFoundError:
            continue
    return Result(False, tr("Programm nicht gefunden: {program}", program=argvs[-1][0]))


def konsole_title_args(title: object) -> list[str]:
    """Konsole-Optionen fuer einen festen Tab- und damit Fenstertitel (lokal und bei ssh).
    ``-p`` trennt mehrere Eigenschaften an „;“ – im Titel wird es zu „,“."""
    text = str(title or "").strip().replace(";", ",")
    if not text:
        return []
    return ["-p", f"tabtitle={text}", "-p", f"RemoteTabTitleFormat={text}"]


def _watch(proc, cmd: str) -> None:
    code = proc.wait()
    if code:
        log.warning("Befehl %r endete mit Exit-Code %s", cmd, code)


@register("command", label=N_("Befehl ausführen"), category="apps", params=[
    Param("command", N_("Befehl"), "text"), Param("terminal", N_("In Terminal"), "bool", True),
    Param("hold", N_("Terminal offen lassen"), "bool", False), Param("workdir", N_("Arbeitsordner"), "dir"),
    Param("title", N_("Fenstertitel (Terminal)"), "text")])
def command(action, ctx, **_):
    cmd = action.get("command", "")
    workdir = action.get("workdir") or None
    try:
        if action.get("terminal", True):
            argv = [KONSOLE]
            if cmd and action.get("hold", False):
                argv.append("--hold")
            if workdir:
                argv += ["--workdir", workdir]
            argv += konsole_title_args(action.get("title"))
            if cmd:
                argv += ["-e", BASH, "-lc", cmd]
            spawn_detached(ctx, argv)
        else:
            if not cmd:
                return Result(False, tr("Kein Befehl angegeben"))
            proc = spawn_detached(ctx, [BASH, "-lc", cmd], workdir)
            # bewusst ein Thread je Befehl statt ``core.workers``: Befehle laufen beliebig
            # lange, ein Worker mit fester Threadzahl liesse spaetere ungeerntet (Zombie)
            # warten. Wie ``asyncio.ThreadedChildWatcher``; der Thread endet mit dem Befehl.
            threading.Thread(target=_watch, args=(proc, cmd), name="command-wait",
                             daemon=True).start()
    except FileNotFoundError as e:
        return _not_found(e, e.filename or str(e), workdir)
    return Result(True)
