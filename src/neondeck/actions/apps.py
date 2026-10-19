"""Aktion „App fokussieren oder starten“.

Laeuft schon ein Fenster der App (KWin-Fensterliste), holt ``ctx.focus`` es nach vorn;
sonst startet die App ueber ``gtk-launch <desktop-id>``, ersatzweise
``kioclient exec <desktop-datei>``. Kacheln des dynamischen Ordners „Fenster“ geben
zusaetzlich ``window`` (KWin-``internalId``) an: dann kommt genau dieses Fenster nach vorn.
Beim Start setzen ``screen``/``place`` das erste neue Fenster der App (``core.placement``).
"""
from __future__ import annotations

from ..core.desktop_apps import find_desktop_file
from ..core.i18n import N_, tr
from ..core.proc import GTK_LAUNCH, KIOCLIENT
from .base import ActionContext, Param, Result, register
from .placing import PLACE_PARAM, SCREEN_PARAM, spawn_placed


def _where(action: dict) -> tuple[object, object]:
    return action.get("screen"), action.get("place")


def _start(ctx: ActionContext, app_id: str, action: dict) -> Result:
    """App starten; ``screen``/``place`` der Aktion gelten fuer ihr erstes neues Fenster."""
    try:
        # "--": Kennung nie als Option lesen
        spawn_placed(ctx, [GTK_LAUNCH, "--", app_id], app_id, *_where(action))
        return Result(True)
    except FileNotFoundError:
        pass
    path = find_desktop_file(app_id)
    if path is None:
        return Result(False, tr("Anwendung nicht gefunden: {app_id}", app_id=app_id))
    try:
        spawn_placed(ctx, [KIOCLIENT, "exec", str(path)], app_id, *_where(action))
    except FileNotFoundError:
        return Result(False, tr("Weder gtk-launch noch kioclient installiert"))
    return Result(True)


@register("app_focus", label=N_("App fokussieren oder starten"), category="apps", params=[
    Param("app_id", N_("Anwendung (Desktop-ID)"), "text"), SCREEN_PARAM, PLACE_PARAM])
def app_focus(action, ctx, **_):
    app_id = str(action.get("app_id") or "").strip()
    window = str(action.get("window") or "")
    if not app_id and not window:
        return Result(False, tr("Keine Anwendung angegeben"))
    if ctx.focus is not None and ctx.focus(app_id, window):
        return Result(True)
    if not app_id:
        return Result(False, tr("Fenster ist nicht mehr offen"))
    return _start(ctx, app_id, action)
