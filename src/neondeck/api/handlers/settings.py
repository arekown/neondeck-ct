"""API-Methoden ``settings.get``/``settings.put``: pruefen gegen das Einstellungsschema, dann
den ``SettingsController`` des Dienstes anwenden lassen."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...core.i18n import N_
from ...core.settings import validate_parts as validate_setting
from ..params import ProfileId, api_method
from ..protocol import ApiError
from . import Handlers
from .profiles import activate, require_known


class SettingsHandlers(Handlers):

    @api_method("settings.get")
    def get(self) -> dict:
        return asdict(self.facade.settings)

    @api_method("settings.put", raw=True)
    def put(self, changes: dict) -> dict:
        for key, value in changes.items():  # erst alles pruefen, dann uebernehmen (nie halb)
            self._check(key, value)
        rest = dict(changes)
        if "active_profile" in rest:  # kann scheitern: zuerst, dann ist noch nichts geaendert
            activate(self.facade, rest.pop("active_profile"))
        if rest:
            self.facade.settings_controller.apply(rest)
        return asdict(self.facade.settings)

    def _check(self, key: str, value: Any) -> None:
        if key == "screensaver_folder":
            if not isinstance(value, str) or (value and not Path(value).expanduser().is_dir()):
                raise ApiError("settings.no_folder", N_("Ordner {path!r} gibt es nicht"),
                               {"path": value})
        elif key == "active_profile":
            require_known(self.facade, ProfileId().check("id", value))
        else:
            bad = validate_setting(key, value)  # Typ und Bereich aus dem Settings-Schema
            if bad is not None:
                raise ApiError("settings.invalid", bad[0], bad[1])
