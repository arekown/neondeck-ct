"""Die Engine (Qt-frei): Ansicht, Eingaben, Aktionen und Anzeige des Geräts.

``Engine`` wird erst beim Zugriff geladen, damit der Editor die kleinen Teile
(``navigation_state``, ``painter``, ``kinds`` …) importieren kann, ohne die ganze Engine zu laden.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Engine

__all__ = ["Engine"]


def __getattr__(name: str):
    if name == "Engine":
        from .engine import Engine
        return Engine
    raise AttributeError(name)
