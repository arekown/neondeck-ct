"""Zwischenablage des Editors: Belegungen und ganze Seiten als eigene MIME-Typen.

* ``application/x-ldl-assignment``: JSON-Liste ``[{"kind", "index", "value"}]`` (Werte als
  Profil-JSON: Taste -> Assignment, Regler -> Encoder, Rad -> Wheel; leer = ``null``).
* ``application/x-ldl-page``: JSON einer Touch-Seite.

Ueber die System-Zwischenablage (``QClipboard``), damit Kopiertes auch in einem anderen
Arbeitsbereich, Profil oder einem neu gestarteten Editor eingefuegt werden kann.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from ...core.errors import LoupedeckError
from ...core.i18n import tr
from ...core.values import is_int, join_errors
from ...device.layout import ControlKind
from ...profile.edit import COUNTS, Item
from ...profile.model import Assignment, Encoder, TouchPage, Wheel, validate_part
from .mime import ASSIGNMENT_MIME, PAGE_MIME, get_json, put_json

log = logging.getLogger(__name__)

PART = {ControlKind.TOUCH: "assignment", ControlKind.ROUND: "assignment",
        ControlKind.SQUARE: "assignment", ControlKind.KNOB: "encoder", ControlKind.WHEEL: "wheel"}


class InvalidPage(LoupedeckError, ValueError):
    """Seite in der Zwischenablage ist kein gueltiges Seiten-JSON."""


def from_json(kind: str, data: dict | None):
    if data is None:
        return None
    if kind == ControlKind.KNOB:
        return Encoder.from_json(data)
    if kind == ControlKind.WHEEL:
        return Wheel.from_json(data)
    return Assignment.from_json(data)


# --- Kodieren -------------------------------------------------------------------------

def encode_items(items: list[Item]) -> list[dict]:
    return [{"kind": i.kind, "index": i.index,
             "value": i.value.to_json() if i.value is not None else None} for i in items]


def decode_items(data: object) -> tuple[list[Item], int]:
    """Elemente aus der Zwischenablage (JSON) und die Zahl der ungueltigen (geprueft wie
    Profile, die ueber die API kommen)."""
    if not isinstance(data, list):
        return [], 1
    out, bad = [], 0
    for d in data:
        if not isinstance(d, dict) or d.get("kind") not in COUNTS or \
                not is_int(d.get("index")):
            bad += 1
            continue
        value = d.get("value")
        errors = validate_part(PART[d["kind"]], value) if value is not None else []
        if errors:
            log.warning("Eingefügtes Element übersprungen: %s", join_errors(errors, 3))
            bad += 1
            continue
        try:
            out.append(Item(d["kind"], d["index"], from_json(d["kind"], value)))
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            log.warning("Eingefügtes Element übersprungen: %s", e)
            bad += 1
    return out, bad


def decode_page(data: object) -> TouchPage:
    """Seite aus der Zwischenablage (JSON); ``InvalidPage`` bei ungueltigem Inhalt."""
    errors = validate_part("page", data)
    if errors:
        raise InvalidPage(join_errors(errors, 3))
    try:
        return TouchPage.from_json(data)
    except (TypeError, ValueError, AttributeError, KeyError) as e:
        raise InvalidPage(str(e)) from None


# --- System-Zwischenablage --------------------------------------------------------------

def _clipboard():
    return QGuiApplication.clipboard()


def put_items(items: list[Item]) -> None:
    _clipboard().setMimeData(put_json(QMimeData(), ASSIGNMENT_MIME, encode_items(items)))


def get_items() -> tuple[list[Item], int]:
    """Elemente und Zahl der ungueltigen (``([], 0)``: nichts in der Zwischenablage)."""
    mime = _clipboard().mimeData()
    if mime is None or not mime.hasFormat(ASSIGNMENT_MIME):
        return [], 0
    try:
        data = get_json(mime, ASSIGNMENT_MIME)
    except ValueError:
        return [], 1
    return decode_items(data)


def has_items() -> bool:
    mime = _clipboard().mimeData()
    return mime is not None and mime.hasFormat(ASSIGNMENT_MIME)


def put_page(page: TouchPage) -> None:
    _clipboard().setMimeData(put_json(QMimeData(), PAGE_MIME, page.to_json()))


def get_page() -> TouchPage | None:
    """Kopierte Seite (``None``: keine da); ``InvalidPage`` bei ungueltigem Inhalt."""
    mime = _clipboard().mimeData()
    if mime is None or not mime.hasFormat(PAGE_MIME):
        return None
    try:
        data = get_json(mime, PAGE_MIME)
    except ValueError:
        raise InvalidPage(tr("kein JSON")) from None
    return decode_page(data)


def has_page() -> bool:
    mime = _clipboard().mimeData()
    return mime is not None and mime.hasFormat(PAGE_MIME)
