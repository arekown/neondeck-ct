"""Fenster platzieren aus Aktionen (``run``, ``app_focus``, ``terminal_layout``): Parameter
und „Wunsch anmelden, starten, bei Fehler verwerfen, Prozess eintragen“ an einer Stelle."""
from __future__ import annotations

from typing import Any

from ..core.i18n import N_
from ..core.placement import PLACES, Ticket
from .base import ActionContext, Param, spawn_detached

# Bildschirm frei (Ausgangsname wie DP-3 oder Lage left/center/right/top/bottom bzw.
# links/mitte/rechts/oben/unten)
SCREEN_PARAM = Param("screen", N_("Bildschirm (z. B. DP-3, links, mitte, rechts, oben)"), "text")
PLACE_PARAM = Param("place", N_("Platz"), "choice", None, PLACES)  # None = "none"


def expect_window(ctx: ActionContext, app_key: str, screen: object,
                  place: object) -> Ticket | None:
    """Platzierungswunsch fuer das naechste Fenster von ``app_key`` (vor dem Start); ``None``
    ohne Wunsch oder ohne Fensterwaechter."""
    if ctx.place is None or (not screen and (place or "none") == "none"):
        return None
    return ctx.place(app_key, str(screen or ""), str(place or "none"))


def pid_of(proc: Any) -> int:
    """Prozessnummer eines Starts (0, wenn unbekannt)."""
    return int(getattr(proc, "pid", 0) or 0)


def spawn_placed(ctx: ActionContext, argv: list[str], app_key: str, screen: object,
                 place: object, workdir: str | None = None) -> tuple[Any, Ticket | None]:
    """``spawn_detached`` mit Platzierung des ersten neuen Fensters auf ``screen``/``place``;
    gibt (Prozess, Ticket | None) zurueck. Scheitert der Start, verfaellt der Wunsch."""
    ticket = expect_window(ctx, app_key, screen, place)
    try:
        proc = spawn_detached(ctx, argv, workdir)
    except Exception:
        if ticket is not None:
            ticket.abandon()
        raise
    if ticket is not None:
        ticket.bind_pid(pid_of(proc))
    return proc, ticket
