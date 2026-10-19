"""Aktionen: KDE-Plasma-Funktionen (Sperren, Bildschirmfoto, Arbeitsflaechen, Uebersicht …)."""
from __future__ import annotations

from ..core.i18n import N_, tr
from ..core.proc import DOLPHIN, EMOJIER, KRUNNER, LOGINCTL, SPECTACLE
from .base import ActionContext, Param, Result, qdbus, register, run_checked, spawn_detached
from .kde_shortcuts import invoke

KWIN_SERVICE = "org.kde.KWin"
VDM_PATH = "/VirtualDesktopManager"
VDM_IFACE = "org.kde.KWin.VirtualDesktopManager"

SHORTCUTS = {"overview": "Overview", "show_desktop": "Show Desktop",
             "desktop_next": "Switch to Next Desktop",
             "desktop_previous": "Switch to Previous Desktop",
             "window_switcher": "Walk Through Windows"}
# screenshot_window: aktives Fenster (-a) ohne Spectacle-Fenster (-b); die KDE-Meldung mit
# Vorschau bleibt an (ohne sie sieht man nicht, dass ein Foto entstanden ist);
# gespeichert/kopiert wird nach den Spectacle-Einstellungen
GUI_PROGRAMS = {"screenshot": [SPECTACLE, "-r"],
                "screenshot_window": [SPECTACLE, "-a", "-b"], "search": [KRUNNER],
                "files": [DOLPHIN], "emoji": [EMOJIER]}
NAMES = ["lock", *GUI_PROGRAMS, *SHORTCUTS, "desktop_add", "desktop_remove"]
LABELS = {"lock": N_("Sperren"), "screenshot": N_("Bildschirmfoto"),
          "screenshot_window": N_("Bildschirmfoto Fenster"), "search": N_("Suche"),
          "files": N_("Dateien"), "emoji": N_("Emoji"), "overview": N_("Übersicht"),
          "show_desktop": N_("Desktop zeigen"), "desktop_next": N_("Nächste Arbeitsfläche"),
          "desktop_previous": N_("Vorherige Arbeitsfläche"),
          "window_switcher": N_("Fenster wechseln"),
          "desktop_add": N_("Arbeitsfläche hinzufügen"),
          "desktop_remove": N_("Arbeitsfläche entfernen")}


def _vdm(ctx: ActionContext, member: str, *args: str) -> Result:
    return qdbus(ctx, KWIN_SERVICE, VDM_PATH, f"{VDM_IFACE}.{member}", *args)


def _desktop_count(ctx: ActionContext) -> tuple[int | None, Result]:
    res = _vdm(ctx, "count")
    if not res.ok:
        return None, res
    try:
        return int(res.message), res
    except ValueError:
        return None, Result(False, tr("Ungültige Desktop-Anzahl: {count}", count=res.message))


def _desktop_add(ctx: ActionContext) -> Result:
    count, res = _desktop_count(ctx)
    if count is None:
        return res
    return _vdm(ctx, "createDesktop", str(count), tr("Arbeitsfläche {number}", number=count + 1))


def _desktop_remove(ctx: ActionContext) -> Result:
    count, res = _desktop_count(ctx)
    if count is None:
        return res
    if count <= 1:
        return Result(True, tr("Nur eine Arbeitsfläche"))
    cur = _vdm(ctx, "current")
    if not cur.ok:
        return cur
    return _vdm(ctx, "removeDesktop", cur.message)


def do_kde(name: str, ctx: ActionContext) -> Result:
    if name in SHORTCUTS:
        res = invoke(ctx, "kwin", SHORTCUTS[name])
    elif name in GUI_PROGRAMS:
        argv = GUI_PROGRAMS[name]
        try:
            spawn_detached(ctx, argv)
        except FileNotFoundError:
            return Result(False, tr("{program} nicht installiert", program=argv[0]))
        return Result(True)
    elif name == "lock":
        res = run_checked(ctx, [LOGINCTL, "lock-session"])
    elif name == "desktop_add":
        res = _desktop_add(ctx)
    elif name == "desktop_remove":
        res = _desktop_remove(ctx)
    else:
        return Result(False, tr("Unbekannte KDE-Aktion: {name}", name=name))
    return Result(res.ok, "" if res.ok else res.message)


@register("kde", label=N_("KDE-Funktion"), category="system", params=[
    Param("name", N_("Funktion"), "choice", "overview", NAMES)])
def kde(action, ctx, **_):
    return do_kde(action.get("name", ""), ctx)


@register("kde_adjust", label=N_("KDE-Funktion je Drehschritt"), category="system", params=[
    Param("left", N_("Links drehen"), "choice", "desktop_previous", NAMES),
    Param("right", N_("Rechts drehen"), "choice", "desktop_next", NAMES)], kinds={"rotate"})
def kde_adjust(action, ctx, *, steps=0, **_):
    name = action.get("right" if steps > 0 else "left", "")
    for _i in range(abs(steps)):
        res = do_kde(name, ctx)
        if not res.ok:
            return res
    return Result(True)
