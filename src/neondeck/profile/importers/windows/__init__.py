"""Uebernahme eines Windows-Loupedeck-Profils (ProfileInfo.json) in das eigene Profilformat.

Aktionszeichenketten haben die Form ``$Plugin___Aktion[___Parameter]``. Makros, Regler-Makros
und Profilaktionen werden darin ueber ihre GUID referenziert. Was sich nicht sicher auf Linux
abbilden laesst, wird zu ``{"type": "unsupported", "original": ...}`` und landet als Text in
der zurueckgegebenen Liste.

Aufgaben: ``actions`` (Aktionszeichenketten), ``macros`` (Makros, Regler-Makros,
Profilaktionen), ``keys`` (Tastennamen), ``icons`` (Tastenbilder, schreibt eingebettete
Symbole ueber ``IconSink``), ``builder`` (Seiten, Regler, Rad, Profil), ``context``
(Tabellen und Meldungen).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...model import Profile
from .actions import ActionMapper
from .builder import ProfileBuilder
from .context import Context
from .icons import IconReader, IconSink
from .keys import keyboard_combo

__all__ = ["convert", "keyboard_combo"]


def convert(profile_info: dict, ict_dir: Path | None, icon_out_dir: Path | None = None,
            images_dir: Path | None = None,
            flatpak_installed: Callable[[str], bool] | None = None,
            ) -> tuple[Profile, list[str]]:
    """Wandelt ein Windows-Profil um; liefert Profil und Liste nicht umsetzbarer Aktionen.

    ``ict_dir`` = ActionIcons-Ordner, ``icon_out_dir`` = Ziel fuer die eingebetteten Symbole,
    ``images_dir`` = ActionImages-Ordner (Standard: neben ``ict_dir``),
    ``flatpak_installed(app_id)`` prueft, ob ein fehlendes Programm als Flatpak da ist
    (Standard: ``flatpak info``).
    """
    ctx = Context(profile_info, flatpak_installed)
    sink = IconSink(Path(icon_out_dir)) if icon_out_dir else None
    return ProfileBuilder(ctx, ActionMapper(ctx), IconReader(ctx, ict_dir, images_dir, sink)).run()
