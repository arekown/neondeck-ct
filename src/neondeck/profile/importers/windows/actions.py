"""Windows-Aktionszeichenketten (``$Plugin___Aktion___Parameter``) -> Aktionen."""
from __future__ import annotations

import re
import shutil

from ....core.i18n import tr
from ...action_types import ActionType
from . import macros
from .context import MAX_DEPTH, Context, split
from .macros import KEYBOARD_TEMPLATE

_DEFAULTWIN: dict[str, dict] = {
    "volume": {"type": ActionType.VOLUME},
    "resetvolume": {"type": ActionType.MUTE_TOGGLE},
    "mediaplaypause": {"type": ActionType.MEDIA, "key": "play_pause"},
    "medianexttrack": {"type": ActionType.MEDIA, "key": "next"},
    "mediaprevtrack": {"type": ActionType.MEDIA, "key": "previous"},
    "brightness": {"type": ActionType.BRIGHTNESS},
    "resetbrightness": {"type": ActionType.BRIGHTNESS_RESET},
    "lockworkstation": {"type": ActionType.KDE, "name": "lock"},
    "windowsscreenshot": {"type": ActionType.KDE, "name": "screenshot"},
    "windowssearch": {"type": ActionType.KDE, "name": "search"},
    "windowsexplorer": {"type": ActionType.KDE, "name": "files"},
    "windowsemoji": {"type": ActionType.KDE, "name": "emoji"},
    "windowsactions": {"type": ActionType.KDE, "name": "overview"},
    "adddesktop": {"type": ActionType.KDE, "name": "desktop_add"},
    "closedesktop": {"type": ActionType.KDE, "name": "desktop_remove"},
    "nextdesktop": {"type": ActionType.KDE, "name": "desktop_next"},
    "previousdesktop": {"type": ActionType.KDE, "name": "desktop_previous"},
}

# Windows-Programm (Dateiname) -> Linux-Befehl
_PROGRAMS = {"firefox.exe": "firefox", "chrome.exe": "google-chrome"}
# Linux-Befehl -> Flatpak-Anwendung, falls der Befehl nicht im PATH liegt
_FLATPAKS = {"firefox": "org.mozilla.firefox"}
# dynamische Ordner von Windows -> eigene Art (``dynamic_folders``)
_DYNAMIC_FOLDERS = {"volumemixeroutputdynamicfolder": "mixer",
                    "volumemixerinputdynamicfolder": "mixer",
                    "taskswitcherdynamicfolder": "windows"}
_DATE_FORMATS = {"date": "date", "weeknumber": "week"}


class ActionMapper:
    """Wandelt Aktionszeichenketten um; Meldungen und Tabellen kommen aus dem ``Context``."""

    def __init__(self, ctx: Context):
        self.ctx = ctx
        # Aktionsname (klein) -> Behandlung (param, original, where)
        self._generic = {
            "@buttonclock": lambda *_: {"type": ActionType.CLOCK},
            "loupedeck.genericplugin.datetimedynamicaction": self._date,
            "loupedeck.genericplugin.stopwatchdynamicaction":
                lambda *_: {"type": ActionType.STOPWATCH},
            "@changeworkspace": self._workspace,
            "@activateloupedeckconfiguration": lambda *_: {"type": ActionType.OPEN_CONFIG},
            "@executeapplication": self._execute_application,
            "@typetext": lambda param, *_: {"type": ActionType.TEXT, "text": param},
            "@sleep": self._sleep,
            "@keyboardkey": self._keyboard,
            "@macro": self._nested(macros.macro),
            "@macroadjustment": self._nested(macros.adjustment),
            "@profileaction": self._nested(lambda _m, *args: macros.profile_action(ctx, *args)),
        }

    def action(self, s: str | None, where: str) -> dict | None:
        if not s:
            return None
        plugin, name, param = split(s)
        if plugin == "defaultwin":
            return self._defaultwin(name.lower(), param, s, where)
        if plugin != "@generic":
            return self.ctx.unsupported(s, where, tr("Plugin {name}", name=plugin))
        handler = self._generic.get(name.lower())
        return handler(param, s, where) if handler else self.ctx.unsupported(s, where)

    def _defaultwin(self, n: str, param: str, s: str, where: str) -> dict | None:
        if n.startswith("#dynamicfolder"):
            kind = _DYNAMIC_FOLDERS.get(param.split("#")[-1].split(".")[-1].lower())
            if kind is None:
                return self.ctx.unsupported(s, where, tr("dynamischer Ordner"))
            return {"type": ActionType.DYNAMIC_FOLDER, "kind": kind}
        if n in _DEFAULTWIN:
            return dict(_DEFAULTWIN[n])
        return self.ctx.unsupported(s, where)

    def _date(self, param: str, s: str, where: str) -> dict:
        fmt = _DATE_FORMATS.get(param.lower())
        if fmt:
            return {"type": ActionType.DATE, "format": fmt}
        return self.ctx.unsupported(s, where)

    def _workspace(self, param: str, s: str, where: str) -> dict:
        ws_id = param.split("|")[-1]
        if ws_id not in self.ctx.workspace_ids:
            return self.ctx.unsupported(s, where, tr("Arbeitsbereich fehlt"))
        return {"type": ActionType.WORKSPACE, "id": ws_id}

    def _sleep(self, param: str, s: str, where: str) -> dict:
        if param.isdigit():
            return {"type": ActionType.SLEEP, "ms": int(param)}
        return self.ctx.unsupported(s, where)

    def _keyboard(self, param: str, s: str, where: str) -> dict:
        return macros.template_action(self.ctx, KEYBOARD_TEMPLATE, {"keyboardKey": param},
                                      s, where)

    def _nested(self, convert):
        """Makro-Aktionen verschachteln sich (hoechstens ``MAX_DEPTH`` tief)."""
        def handle(param: str, s: str, where: str) -> dict | None:
            ctx = self.ctx
            if ctx.depth >= MAX_DEPTH:
                return ctx.unsupported(s, where, tr("zu tief verschachtelt"))
            ctx.depth += 1
            try:
                return convert(self, param, s, where)
            finally:
                ctx.depth -= 1
        return handle

    def _execute_application(self, path: str, original: str, where: str) -> dict:
        ctx = self.ctx
        target = path.strip()
        if re.match(r"https?://", target, re.IGNORECASE):
            return {"type": ActionType.OPEN, "target": target}
        exe = re.split(r"[\\/]", target)[-1].lower()
        command = _PROGRAMS.get(exe)
        if command is None:
            return ctx.unsupported(original, where, tr("Windows-Programm"))
        if shutil.which(command) is None:
            app_id = _FLATPAKS.get(command)
            if app_id and ctx.flatpak(app_id):
                return {"type": ActionType.RUN, "command": f"flatpak run {app_id}"}
            ctx.note(where, tr("Programm „{name}“ ist nicht installiert", name=command))
        return {"type": ActionType.RUN, "command": command}
