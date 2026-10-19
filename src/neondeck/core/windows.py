"""Fenster, wie KWin sie meldet (Qt-frei; Dynamic Mode, dynamische Ordner, Dienst)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    """Ein Fenster, wie KWin es meldet (``internal_id`` nur aus der Fensterliste)."""

    resource_class: str
    desktop_file: str
    caption: str
    pid: int
    internal_id: str = ""

    @property
    def app_key(self) -> str:
        """Kennung der Anwendung (``desktopFileName`` bevorzugt), klein geschrieben."""
        return (self.desktop_file or self.resource_class).lower()

    def matches(self, app_id: str) -> bool:
        """Gehoert das Fenster zur App ``app_id`` (desktopFileName oder resourceClass,
        Gross/klein egal; ``lower()`` wie ``toLowerCase()`` im KWin-Skript)?"""
        key = (app_id or "").lower()
        return bool(key) and key in (self.desktop_file.lower(), self.resource_class.lower())
