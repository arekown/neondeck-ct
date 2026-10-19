"""Bilder der Anzeige-Aktionen (Uhr, Datum, Stoppuhr), jedes Mal neu aus der Uhrzeit."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..core.i18n import tr
from .images import TileSpec
from .text import weekday_short


class Elapsed(Protocol):
    """Was die Stoppuhr-Kachel zeigt (``engine.stopwatch.Stopwatch``)."""

    def display(self, now: float) -> str: ...


def live_image(action: dict, now: datetime, state: Elapsed | None = None
               ) -> TileSpec | None:
    t = action.get("type")
    if t == "clock":
        return TileSpec(text=now.strftime("%H:%M"),
                        value=f"{weekday_short(now.weekday())} {now.day:02d}.{now.month:02d}.")
    if t == "date":
        if action.get("format") == "week":
            return TileSpec(text=tr("KW {week}", week=now.isocalendar().week))
        return TileSpec(text=f"{now.day:02d}.{now.month:02d}.")
    if t == "stopwatch" and state is not None:
        return TileSpec(text=state.display(now.timestamp()))
    return None
