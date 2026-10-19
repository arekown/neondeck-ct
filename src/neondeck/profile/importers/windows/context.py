"""Gemeinsamer Zustand einer Umwandlung: Tabellen aus ``ProfileInfo.json``, Meldungen."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ....core import proc
from ....core.i18n import tr

SEP = "___"
MAX_DEPTH = 5
FLATPAK_TIMEOUT_S = 1.5  # laeuft auch im Import-Pfad des Editors (GUI-Thread)


def flatpak_app_installed(app_id: str) -> bool:
    """Ist die Flatpak-Anwendung ``app_id`` installiert (``flatpak info``)?"""
    try:
        return proc.run([proc.FLATPAK, "info", app_id], stdout=proc.DEVNULL,
                        stderr=proc.DEVNULL, timeout=FLATPAK_TIMEOUT_S).returncode == 0
    except (OSError, proc.SubprocessError):
        return False


def split(action: str) -> tuple[str, str, str]:
    """``$Plugin___Aktion___Parameter`` -> (Plugin klein, Aktion, Parameter)."""
    parts = (action[1:] if action.startswith("$") else action).split(SEP)
    plugin = parts[0].lower()
    name = parts[1] if len(parts) > 1 else ""
    return plugin, name, SEP.join(parts[2:])


def nocase(d: dict | None) -> dict:
    return {k.lower(): v for k, v in (d or {}).items() if k != "$type"}


def display(d: dict | None) -> str:
    return ((d or {}).get("displayName") or "").replace("\\n", "\n")


def unsupported_action(original: str) -> dict:
    return {"type": "unsupported", "original": original}


class Context:
    """Was Aktions-, Makro-, Symbol- und Seitenumwandlung teilen."""

    def __init__(self, info: dict, flatpak: Callable[[str], bool] | None = None):
        self.info = info
        self.flatpak = flatpak or flatpak_app_installed
        self.macros = {m.get("name", "").lower(): m for m in info.get("macroCommands") or []}
        self.adjustments = {m.get("name", "").lower(): m
                            for m in info.get("macroAdjustments") or []}
        self.profile_actions = {a.get("name", "").split(SEP)[-1].lower(): a
                                for a in info.get("profileActions") or []}
        self.workspace_ids: set[str] = set()
        self.messages: list[str] = []
        self.depth = 0

    def note(self, where: str, text: str) -> None:
        line = f"{where}: {text}"
        if line not in self.messages:
            self.messages.append(line)

    def unsupported(self, original: str, where: str, reason: str = "") -> dict:
        if reason:
            self.note(where, tr("nicht umsetzbar ({reason}): {original}", reason=reason,
                                original=original))
        else:
            self.note(where, tr("nicht umsetzbar: {original}", original=original))
        return unsupported_action(original)

    def display_name(self, s: str) -> str:
        """Anzeigename von Makro, Regler-Makro oder Profilaktion hinter ``s`` (sonst leer)."""
        plugin, name, param = split(s)
        if plugin != "@generic":
            return ""
        table = {"@macro": self.macros, "@macroadjustment": self.adjustments,
                 "@profileaction": self.profile_actions}.get(name.lower())
        return display(table.get(param.lower())) if table is not None else ""


class ActionSource(Protocol):
    """Was Makros von der Aktionsumwandlung brauchen (Aktionen koennen Makros enthalten)."""

    ctx: Context

    def action(self, s: str | None, where: str) -> dict | None: ...
