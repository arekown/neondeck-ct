"""Aktionsgruppen, die die Engine selbst behandelt, ohne Qt.

* ``NAV_TYPES``: Navigation laeuft direkt im Engine-Thread (``Engine.call``), nicht im Executor.
* ``LIVE_TYPES``: Anzeige-Kacheln (Uhr, Datum, Stoppuhr) zeichnen sich selbst und loesen
  nichts aus; der Editor bietet fuer sie keine Gesten an.
"""
from __future__ import annotations

NAV_TYPES = frozenset({"workspace", "page_next", "page_previous", "page", "open_config", "profile",
                       "folder", "folder_back", "dynamic_folder"})
LIVE_TYPES = frozenset({"clock", "date", "stopwatch"})
STOPWATCH = "stopwatch"  # misst die Druckdauer selbst (kein Halten/Doppeltippen)


def typed(action: dict | None) -> bool:
    """Belegte Aktion (dict mit ``type``)?"""
    return isinstance(action, dict) and bool(action.get("type"))


def action_type(action: dict | None) -> str | None:
    """``type`` einer Aktion (``None`` ohne Aktion oder ohne Typ)."""
    return (action.get("type") or None) if isinstance(action, dict) else None
