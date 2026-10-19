"""Navigations-Aktionen; alle gehen ueber ``ctx.engine_call`` an die Engine."""
from __future__ import annotations

from ..core.i18n import N_
from .base import Param, Result, register


def _nav(name: str, ctx, params: dict | None = None) -> Result:
    ctx.engine_call(name, params or {})
    return Result(True)


@register("workspace", label=N_("Arbeitsbereich"), category="navigation", params=[Param("id", N_("Arbeitsbereich"), "text")])
def workspace(action, ctx, **_):
    return _nav("workspace", ctx, {"id": action.get("id")})


@register("page_next", label=N_("Nächste Seite"), category="navigation")
def page_next(action, ctx, **_):
    return _nav("page_next", ctx)


@register("page_previous", label=N_("Vorherige Seite"), category="navigation")
def page_previous(action, ctx, **_):
    return _nav("page_previous", ctx)


@register("page", label=N_("Seite"), category="navigation", params=[Param("index", N_("Seitennummer"), "int", 0)])
def page(action, ctx, **_):
    return _nav("page", ctx, {"index": action.get("index", 0)})


@register("open_config", label=N_("Konfiguration öffnen"), category="navigation")
def open_config(action, ctx, **_):
    return _nav("open_config", ctx)


@register("profile", label=N_("Profil"), category="navigation", params=[Param("id", N_("Profil"), "text")])
def profile(action, ctx, **_):
    return _nav("profile", ctx, {"id": action.get("id")})


@register("folder", label=N_("Ordner öffnen"), category="navigation",
          params=[Param("page", N_("Ordnerseite"), "text"),
                  Param("auto_exit", N_("Nach Aktion zurück"), "bool", False)])
def folder(action, ctx, **_):
    return _nav("folder", ctx, {"page": action.get("page"),
                                "auto_exit": bool(action.get("auto_exit", False))})


@register("folder_back", label=N_("Ordner: Zurück"), category="navigation")
def folder_back(action, ctx, **_):
    return _nav("folder_back", ctx)


DYNAMIC_KINDS = ["windows", "mixer"]


@register("dynamic_folder", label=N_("Dynamischer Ordner"), category="navigation",
          params=[Param("kind", N_("Inhalt"), "choice", "windows", DYNAMIC_KINDS)])
def dynamic_folder(action, ctx, **_):
    return _nav("dynamic_folder", ctx, {"kind": action.get("kind")})
