"""Eigene MIME-Typen des Editors (Ziehen & Ablegen, Zwischenablage) und ihr JSON-Inhalt."""
from __future__ import annotations

import json

from PySide6.QtCore import QMimeData

ACTION_MIME = "application/x-ldl-action"          # Aktionsvorlage aus der Bibliothek
CONTROLS_MIME = "application/x-ldl-controls"      # Ziehen zwischen Elementen: Liste der Quellen
ASSIGNMENT_MIME = "application/x-ldl-assignment"  # kopierte Belegungen
PAGE_MIME = "application/x-ldl-page"              # kopierte Touch-Seite


def put_json(mime: QMimeData, kind: str, data: object) -> QMimeData:
    """``data`` als JSON (UTF-8) unter dem MIME-Typ ``kind`` ablegen; gibt ``mime`` zurueck."""
    mime.setData(kind, json.dumps(data).encode("utf-8"))
    return mime


def get_json(mime: QMimeData, kind: str) -> object:
    """JSON-Inhalt unter ``kind``; ``ValueError``, wenn er fehlt oder kein JSON ist."""
    return json.loads(bytes(mime.data(kind)).decode("utf-8"))
