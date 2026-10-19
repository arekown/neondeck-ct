"""Waehlbare Ziele der Navigationsaktionen (Arbeitsbereich, Profil, Ordnerseite) und die
Listen des Dienstes (Anwendungen, KDE-Kürzel) fuer die Aktionsformulare."""
from __future__ import annotations

from dataclasses import dataclass, field

from .param_widgets import Catalog

# Parameter, die statt Freitext aus einer Liste gewaehlt werden: (Typ, Parameter) -> Liste
NAV_PICKERS = {("workspace", "id"): "workspaces", ("profile", "id"): "profiles",
               ("folder", "page"): "folder_pages"}


@dataclass
class NavTargets:
    """Waehlbare Ziele fuer Navigationsaktionen: ``(id, Name)`` je Arbeitsbereich/Profil."""
    workspaces: list[tuple[str, str]] = field(default_factory=list)
    profiles: list[tuple[str, str]] = field(default_factory=list)
    folder_pages: list[tuple[str, str]] = field(default_factory=list)  # Ordnerseiten des AB
    catalog: Catalog | None = None  # Anwendungen, KDE-Kürzel (vom Dienst)

    def choices(self, action_type: str | None, param: str) -> list[tuple[str, str]] | None:
        which = NAV_PICKERS.get((action_type, param))
        return None if which is None else getattr(self, which)
