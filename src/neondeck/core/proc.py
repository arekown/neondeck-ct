"""Externe Programme: kurze Aufrufe mit Zeitlimit, losgeloeste Starts, Programmnamen.

Der einzige Ort, der ``subprocess`` benutzt. Aktionen gehen ueber ``ActionContext.run`` und
``ActionContext.popen`` (Tests ersetzen sie), die auf ``run`` und ``subprocess.Popen`` zeigen.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from .i18n import tr

# Programmnamen (ein Ort, damit Diagnose, Aktionen und Dienst dieselben meinen)
PACTL = "pactl"
WPCTL = "wpctl"
QDBUS = "qdbus"
KONSOLE = "konsole"
KIOCLIENT = "kioclient"
GIO = "gio"
GTK_LAUNCH = "gtk-launch"
XDG_OPEN = "xdg-open"
SPECTACLE = "spectacle"
KRUNNER = "krunner"
DOLPHIN = "dolphin"
EMOJIER = "plasma-emojier"
LOGINCTL = "loginctl"
WL_COPY = "wl-copy"
FLATPAK = "flatpak"
NVIDIA_SMI = "nvidia-smi"
SETPRIV = "setpriv"
BASH = "bash"
DDCUTIL = "ddcutil"

RUN_TIMEOUT_S = 10.0
DEVNULL = subprocess.DEVNULL
SubprocessError = subprocess.SubprocessError
TimeoutExpired = subprocess.TimeoutExpired
CompletedProcess = subprocess.CompletedProcess
Popen = subprocess.Popen

Runner = Callable[..., subprocess.CompletedProcess]


def run(argv: list[str], timeout: float = RUN_TIMEOUT_S, **kw) -> subprocess.CompletedProcess:
    """Kurzer Aufruf mit Textausgabe und Zeitlimit (``check=False``).

    Mit ``stdout``/``stderr`` faellt das Mitschneiden weg (z. B. DEVNULL fuer Programme wie
    wl-copy, die sich abspalten und geerbte Pipes offen halten)."""
    opts: dict[str, Any] = {"text": True, "timeout": timeout, "check": False}
    if "stdout" not in kw and "stderr" not in kw:
        opts["capture_output"] = True
    return subprocess.run(argv, **(opts | kw))  # noqa: PLW1510  # check=False steckt in opts


def run_checked(argv: list[str], *, run: Runner = run) -> tuple[bool, str]:
    """``(True, stdout)`` bei Exit-Code 0, sonst ``(False, Meldung)``; fehlendes Programm
    ebenso (``FileNotFoundError``), andere Fehler gehen weiter."""
    try:
        p = run(argv)
    except FileNotFoundError:
        return False, tr("{program} nicht installiert", program=argv[0])
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()
        return False, tr("{program} fehlgeschlagen: {detail}", program=argv[0], detail=detail) if detail \
            else tr("{program} fehlgeschlagen", program=argv[0])
    return True, (p.stdout or "").strip()


def spawn_detached(argv: list[str], cwd: str | None = None, env: dict | None = None, *,
                   popen: Callable[..., Any] | None = None):
    """Programm losgeloest starten (eigene Sitzung, keine geerbten Ein-/Ausgaben).

    ``FileNotFoundError`` bei fehlendem Programm oder Arbeitsordner geht an den Aufrufer."""
    return (popen or Popen)(argv, cwd=cwd or None, env=env, start_new_session=True, stdin=DEVNULL,
                 stdout=DEVNULL, stderr=DEVNULL, close_fds=True)


def qdbus_argv(service: str, path: str, method: str, *args: object,
               literal: bool = False) -> list[str]:
    """Befehlszeile fuer einen D-Bus-Aufruf ueber das Werkzeug ``qdbus``."""
    return [QDBUS, *(["--literal"] if literal else []), service, path, method,
            *(str(a) for a in args)]
