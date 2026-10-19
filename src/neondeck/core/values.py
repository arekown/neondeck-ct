"""Kleine Qt-freie Werte-Helfer, die Einstellungen, API, Engine und Editor gemeinsam nutzen."""
from __future__ import annotations

from collections.abc import Iterable

from .i18n import N_, tr

# Anzeigetext der Lautstaerke-Aktionen, wenn stumm (ausgewertet wird ``Result.muted``)
MUTED_MESSAGE = N_("stumm")
EPS = 1e-6  # Toleranz beim Vergleich von Zeitpunkten (Gleitkomma)


def is_int(v: object) -> bool:
    """Ganze Zahl im JSON-Sinn: ``int``, aber nicht ``bool``."""
    return isinstance(v, int) and not isinstance(v, bool)


def parse_view(v: object, *, min_page: int | None = None) -> tuple[str, int] | None:
    """Ansicht ``{"workspace": str, "page": int}`` als ``(workspace, page)``, sonst None.

    ``min_page``: kleinste erlaubte Seite (None = keine Untergrenze)."""
    if not isinstance(v, dict):
        return None
    ws, page = v.get("workspace"), v.get("page")
    if not isinstance(ws, str) or not is_int(page):
        return None
    if min_page is not None and page < min_page:
        return None
    return ws, page


def join_errors(errors: Iterable[str], limit: int = 5, *, with_more: bool = False) -> str:
    """Die ersten ``limit`` Fehler mit „; “ verbunden; ``with_more`` haengt
    „ (und n weitere)“ an, wenn es mehr gibt."""
    errors = list(errors)
    text = "; ".join(errors[:limit])
    more = len(errors) - limit
    if with_more and more > 0:
        text += tr(" (und {count} weitere)", count=more)
    return text
