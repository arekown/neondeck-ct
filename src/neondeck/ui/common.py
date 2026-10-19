"""Was Dienst- und Editor-Prozess gemeinsam brauchen (ohne Geraet, Engine oder Tray)."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from ..core import i18n

log = logging.getLogger(__name__)

APP_NAME = "Neondeck CT"
DESKTOP_NAME = "neondeck-ct"
DRAIN_S = 3.0  # beim Schliessen: so lange auf Speicher-Bestaetigungen warten
STATUS_MS = 5000       # Statusmeldung im Editor: so lange sichtbar
STATUS_LONG_MS = 8000  # ... laengere Meldungen (Aufzaehlungen)

Request = Callable[..., Any]  # Anfrage an den Dienst: ``ServiceLink.request(method, params)``

_translators: list[QTranslator] = []  # installiert; Referenz halten, sonst raeumt Python sie weg


def install_translations(locale: QLocale | None = None) -> bool:
    """Qt-eigene Texte (Knoepfe „Abbrechen“, „Ja“ …) in der Systemsprache; einmalig.

    ``False``, wenn es keine passende Uebersetzung gibt (dann bleibt Qt englisch).
    """
    app = QCoreApplication.instance()
    if app is None:
        return False
    if _translators:
        return True
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    tr = QTranslator()
    if not tr.load(locale or QLocale.system(), "qtbase", "_", folder):
        log.info("Keine Qt-Übersetzung für %s in %s", (locale or QLocale.system()).name(),
                 folder)
        return False
    app.installTranslator(tr)
    _translators.append(tr)
    return True


def remove_translations() -> None:
    app = QCoreApplication.instance()
    while _translators:
        tr = _translators.pop()
        if app is not None:
            app.removeTranslator(tr)


def apply_language(setting: str) -> str:
    """Sprache des Prozesses aus der Einstellung ``language`` (``auto`` oder Code): eigene
    Texte (``core.i18n``) und Qt-eigene Texte mit demselben Code; liefert den Code."""
    code = i18n.set_language(setting)
    remove_translations()
    install_translations(QLocale(code))
    return code
