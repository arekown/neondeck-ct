"""Konsole starten und steuern: Layout- und Register-Dateien, Befehlszeilen, D-Bus der
laufenden Konsole (``org.kde.konsole-<pid>``; belegt an Konsole 26.08.1).

* Layoutdatei (``konsole --layout``): ``{"Orientation": "Horizontal"|"Vertical", "Widgets":
  [{"SessionRestoreId": 0, "Command": "..."}, ...]}`` – je Eintrag eine geteilte Ansicht.
  Ohne ``SessionRestoreId`` legt Konsole keine Ansicht an; ``Command`` wird in die frische
  Shell getippt (nach ``exit`` von ``ssh`` bleibt die lokale Shell offen).
* ``-p tabtitle=`` wirkt auf Layout-Ansichten nicht: der Titel kommt danach ueber D-Bus
  (``/Sessions/<n>`` ``setTabTitleFormat`` 0 = lokal, 1 = ssh). ``--separate`` sorgt fuer
  einen eigenen Prozess, damit der Dienstname bekannt ist.
* Register (``--tabs-from-file``): je Zeile ``title: …;; command: …``. Konsole legt dabei
  immer ein zusaetzliches Standard-Register ans Ende, und ueber D-Bus laesst sich keines
  schliessen. Darum steht das letzte Register nicht in der Datei, sondern in ``-e``; sein
  Titel kommt ueber D-Bus. Befehle laufen als ``<befehl>; exec "$SHELL"``.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..core.fileio import runtime_tempfile
from ..core.proc import KONSOLE
from .base import ActionContext, qdbus

KEEP_SHELL = '; exec "$SHELL"'  # nach Ende des Befehls (ssh) bleibt das Register offen
SESSION_TRIES = 25     # Konsole meldet seine Ansichten kurz nach dem Start auf D-Bus
SESSION_RETRY_S = 0.2


# --- Dateien und Befehlszeilen -----------------------------------------------------------

def layout_json(win: dict) -> dict:
    widgets = []
    for cmd in win["commands"]:
        leaf: dict = {"SessionRestoreId": 0}  # 0 = neue Ansicht (ohne Schluessel: keine)
        if cmd:
            leaf["Command"] = cmd
        widgets.append(leaf)
    return {"Orientation": "Vertical" if win.get("split") == "vertical" else "Horizontal",
            "Widgets": widgets}


def _clean_line(text: str) -> str:
    """Ein Wert der Register-Datei: Zeilenumbruch und ``;;`` (Feldtrenner) entschaerfen."""
    return " ".join(text.split()).replace(";;", "; ;")


def tabs_file_text(win: dict) -> str:
    """Zeilen der Register-Datei: alle Register ausser dem letzten (das laeuft ueber ``-e``)."""
    lines = []
    for tab in win["tabs"][:-1]:
        title = _clean_line(tab["title"] or win["title"])
        line = f"title: {title}"
        if tab["command"]:
            line += f";; command: {_clean_line(tab['command'])}{KEEP_SHELL}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def tabs_argv(win: dict, path: str) -> list[str]:
    """Konsole-Befehlszeile eines Fensters mit Registern; ``path`` = Register-Datei."""
    argv = [KONSOLE, "--separate"]
    if len(win["tabs"]) > 1:
        argv += ["--tabs-from-file", path]
    last = win["tabs"][-1]["command"]
    if last:
        argv += ["-e", "sh", "-c", f"{last}{KEEP_SHELL}"]
    return argv


def window_file(win: dict) -> Path:
    """Register- bzw. Layoutdatei des Fensters im Laufzeitordner (Aufrufer loescht sie)."""
    if win.get("tabs"):
        return runtime_tempfile("neondeck-ct-tabs-", ".txt", tabs_file_text(win))
    return runtime_tempfile("neondeck-ct-layout-", ".json", json.dumps(layout_json(win)))


def window_argv(win: dict, path: Path) -> list[str]:
    if win.get("tabs"):
        return tabs_argv(win, str(path))
    return [KONSOLE, "--separate", "--layout", str(path)]


# --- D-Bus der laufenden Konsole ---------------------------------------------------------

class KonsoleBus:
    """Eine laufende Konsole (Prozess ``pid``) ueber ``qdbus``; ``ctx.sleep`` wartet."""

    def __init__(self, ctx: ActionContext, pid: int) -> None:
        self._ctx, self._service = ctx, f"org.kde.konsole-{pid}"

    def _call(self, path: str, method: str, *args: str) -> str | None:
        res = qdbus(self._ctx, self._service, path, method, *args)
        return res.message if res.ok else None

    def sessions(self) -> list[str]:
        """Ansichten (Session-Nummern); leer, wenn sich die Konsole nicht meldet. Wartet kurz
        und begrenzt: Konsole legt den D-Bus-Dienst erst beim Start an."""
        for _ in range(SESSION_TRIES):
            out = self._call("/Windows/1", "org.kde.konsole.Window.sessionList")
            ids = [s.strip() for s in (out or "").split() if s.strip().isdigit()]
            if ids:
                return ids
            self._ctx.sleep(SESSION_RETRY_S)
        return []

    def set_title(self, sessions: list[str], title: str) -> None:
        for sid in sessions:
            for context in ("0", "1"):  # 0 = lokale Shell, 1 = ssh
                self._call(f"/Sessions/{sid}", "org.kde.konsole.Session.setTabTitleFormat",
                           context, title)

    def show(self, session: str) -> None:
        self._call("/Windows/1", "org.kde.konsole.Window.setCurrentSession", session)
