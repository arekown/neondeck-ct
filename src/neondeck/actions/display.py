"""Anzeige-Aktionen (Uhr, Datum, Stoppuhr): nur die Eintraege fuer Auswahl und Profil; die
Engine zeichnet sie (``render.live.live_image``) und haelt die Stoppuhren (``engine.stopwatch``)."""
from __future__ import annotations

from ..core.i18n import N_
from .base import Param, register


@register("clock", label=N_("Uhr"), category="display")
def clock(action, ctx, **_):
    return None


@register("date", label=N_("Datum"), category="display", params=[
    Param("format", N_("Format"), "choice", "date", ["date", "week"])])
def date(action, ctx, **_):
    return None


@register("stopwatch", label=N_("Stoppuhr"), category="display")
def stopwatch(action, ctx, **_):
    return None  # die Engine haelt je Bedienelement eine Stoppuhr und ruft deren press()
