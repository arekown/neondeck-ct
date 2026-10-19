"""Ausnahmen des Programms: eine gemeinsame Basis, damit Aufrufer eigene Fehler von
Programmierfehlern trennen koennen."""
from __future__ import annotations


class LoupedeckError(Exception):
    """Basis aller eigenen Ausnahmen (Text fuer den Benutzer, deutsch)."""


class ProfileFormatError(LoupedeckError, ValueError):
    """Profil-JSON hat nicht das erwartete Format (fremde oder kaputte Datei)."""


class DBusError(LoupedeckError):
    """Ein D-Bus-Aufruf kam mit einer Fehlerantwort zurueck."""
