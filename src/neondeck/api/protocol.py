"""Protokoll der lokalen JSON-Schnittstelle (ohne Qt).

Eine JSON-Zeile je Nachricht (UTF-8, ``\\n``):

* Anfrage ``{"id": n, "method": str, "params": {}}``
* Antwort ``{"id": n, "result": ...}`` oder ``{"id": n, "error": str, "code": str,
  "message": str, "params": {}}``: ``error`` ist der fertige Text fuer den Benutzer (auch
  fuer aeltere Clients), ``code`` die maschinenlesbare Art (``ERR_*``, z. B.
  ``profile.not_found``), ``message`` der deutsche Quelltext mit Platzhaltern
  (``"Profil {id!r} gibt es nicht"``) und ``params`` die Werte dazu (fehlt, wenn leer).
  Der Client zeigt ``tr(message, **params)`` in seiner eigenen Sprache.
* Ereignis ``{"event": str, "data": {}}`` (nur an Verbindungen, die ``subscribe`` aufgerufen
  haben)

Laengere Zeilen als ``MAX_LINE`` beenden die Verbindung.
"""
from __future__ import annotations

import json
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.errors import LoupedeckError
from ..core.i18n import N_, tr
from ..core.values import is_int
from ..device.layout import CONTROL_COUNTS, ControlRef
from ..device.protocol import ButtonEvent, Event, RotateEvent, TouchEvent, WheelTouchEvent

SERVER_NAME = "neondeck-ct"  # Name ohne Laufzeitordner (Qt legt ihn im Temp-Ordner an)
SOCKET_FILE = "neondeck-ct.sock"
LEGACY_NAME = SERVER_NAME  # Adresse aelterer Versionen (vor dem Laufzeitordner); Tests biegen um
MAX_LINE = 16 * 1024 * 1024
EDITOR_ROLE = "editor"  # Rolle des Editors beim Abonnieren (``subscribe``)
SHOW_FAILED = N_("Profil lässt sich nicht anzeigen")  # Profil geladen, aber nicht darstellbar
DISCONNECTED = N_("Verbindung zum Dienst getrennt")
NOT_CONNECTED = N_("Nicht mit dem Dienst verbunden")
CONNECT_TIMEOUT_S = 2.0         # CLI: Dienst laeuft oder nicht
EDITOR_CONNECT_TIMEOUT_S = 5.0  # Editor: Dienst darf gerade erst starten

# Fehlercodes, die Programme auswerten (die uebrigen stehen an der Fehlerstelle)
ERR_GENERIC = "error"                   # ohne genauere Art (z. B. aeltere Dienste)
ERR_INTERNAL = "internal"               # Programmfehler im Dienst
ERR_SHOW_FAILED = "profile.show_failed"  # Profil geladen, aber nicht darstellbar
ERR_DISCONNECTED = "connection.lost"    # Verbindung waehrend der Anfrage getrennt
ERR_NOT_CONNECTED = "connection.none"   # keine Verbindung
ERR_NO_REPLY = "connection.no_reply"    # keine Antwort in der Wartezeit

# Bedienelemente und Anzahl (Index ab 0); das Rad hat keinen Index.
REF_COUNTS = CONTROL_COUNTS
REF_LIST = "touch:0-11, round:0-7, square:0-11, knob:0-5, strip:0-5"


def ref_help() -> str:
    """Gueltige Bedienelemente als Hilfetext (in der Sprache des Prozesses)."""
    return tr("{refs} oder wheel", refs=REF_LIST)

EVENT_TYPES: dict[str, type] = {"button": ButtonEvent, "rotate": RotateEvent,
                                "touch": TouchEvent, "wheel_touch": WheelTouchEvent}
_EVENT_NAMES = {cls: name for name, cls in EVENT_TYPES.items()}


def socket_path() -> str:
    """Adresse der API (zugleich Einzelinstanz-Sperre) fuer Dienst, Editor und CLI.

    Voller Pfad im Laufzeitordner des Benutzers (``$XDG_RUNTIME_DIR``, nur fuer ihn
    zugaenglich), sonst der einfache Name (dann im Temp-Ordner, wie Qt ihn anlegt).
    """
    runtime = paths.runtime_dir()
    return str(runtime / SOCKET_FILE) if runtime else SERVER_NAME


def local_socket_file(name: str) -> Path:
    """Datei des Sockets ``name`` wie bei ``QLocalSocket``/``QLocalServer``: ein absoluter
    Pfad bleibt, ein einfacher Name liegt im Temp-Ordner (``$TMPDIR``, sonst ``/tmp``)."""
    if name.startswith("/"):
        return Path(name)
    return Path(os.environ.get("TMPDIR") or "/tmp") / name


def legacy_names() -> list[str]:
    """Weitere Adressen, unter denen eine aeltere laufende Instanz lauschen kann (nur fuer
    die Standardadresse fragen: Einzelinstanz, Editor)."""
    return [LEGACY_NAME] if socket_path() != LEGACY_NAME else []


class ErrorText(str):
    """Fehlertext einer Antwort mit ``code``, ``params`` und ``message`` (deutscher
    Quelltext; Rueckrufe bekommen Fehler als Text, wer die Art braucht, liest
    ``error_code``). Der Text selbst ist ``tr(message, **params)``."""

    code: str
    params: dict
    message: str

    def __new__(cls, message: str, code: str = ERR_GENERIC,
                params: dict | None = None) -> ErrorText:
        params = dict(params or {})
        text = super().__new__(cls, tr(message, **params))
        text.code, text.params, text.message = code, params, message
        return text


def error_code(error: object) -> str:
    """Code eines Fehlers (``ApiError``, ``ErrorText``); einfacher Text: ``ERR_GENERIC``."""
    return getattr(error, "code", ERR_GENERIC)


class ApiError(LoupedeckError):
    """Fehlerantwort der Schnittstelle: ``code`` (maschinenlesbar), ``message`` (deutscher
    Quelltext mit Platzhaltern, z. B. ``"Profil {id!r} gibt es nicht"``) und ``params``
    (Werte dazu). ``str(e)`` ist ``tr(message, **params)`` in der Sprache des Prozesses."""

    def __init__(self, code: str, message: str, params: dict | None = None) -> None:
        params = dict(params or {})
        super().__init__(tr(message, **params))
        self.code, self.message, self.params = code, message, params

    @classmethod
    def from_error(cls, error: str) -> ApiError:
        """Aus dem Fehlertext eines Rueckrufs (``ErrorText`` behaelt Code, Quelltext und
        Werte)."""
        return cls(error_code(error), getattr(error, "message", str(error)),
                   getattr(error, "params", None))


def error_reply(rid: object, error: object) -> dict:
    """Antwort-Objekt fuer einen Fehler (Text, Code, deutscher Quelltext und – wenn
    vorhanden – Werte)."""
    reply = {"id": rid, "error": str(error), "code": error_code(error),
             "message": getattr(error, "message", str(error))}
    params = getattr(error, "params", None)
    if params:
        reply["params"] = params
    return reply


def reply_error(msg: dict) -> ErrorText | None:
    """Fehler einer Antwort als ``ErrorText`` in der Sprache dieses Prozesses (``None`` ohne
    Fehler); aeltere Dienste senden nur den Text (dann ist er der Quelltext)."""
    if msg.get("error") is None:
        return None
    code = msg.get("code")
    params = msg.get("params")
    message = msg.get("message")
    return ErrorText(message if isinstance(message, str) else str(msg["error"]),
                     code if isinstance(code, str) else ERR_GENERIC,
                     params if isinstance(params, dict) else None)


def switch_error_text(err: BaseException) -> str:
    """Meldung fuer einen gescheiterten Profilwechsel: ``SHOW_FAILED`` nur, wenn sich das
    Profil nicht darstellen liess; Dienst-/Verbindungsfehler (offline, keine Antwort …)
    behalten ihren eigenen Text."""
    text = str(err)
    if isinstance(err, ApiError):
        return text if err.code == ERR_SHOW_FAILED else tr(
            "Profilwechsel fehlgeschlagen: {error}", error=text)
    return tr("{what}: {error}", what=tr(SHOW_FAILED), error=text)


class LineTooLong(LoupedeckError, ValueError):
    """Eine Zeile ist laenger als erlaubt."""


class LineBuffer:
    """Setzt Zeilen aus beliebig zerstueckelten Bytes zusammen."""

    def __init__(self, limit: int = MAX_LINE) -> None:
        self._limit = limit
        self._buf = bytearray()

    @property
    def pending(self) -> int:
        """Bytes einer noch unvollstaendigen Zeile."""
        return len(self._buf)

    def feed(self, data: bytes) -> list[bytes]:
        """Neue Bytes; liefert alle vollstaendigen Zeilen (ohne ``\\n``).

        Wirft ``LineTooLong``, sobald eine Zeile ``limit`` Bytes uebersteigt (auch eine
        noch unvollstaendige) – die Verbindung ist dann nicht mehr zu retten.
        """
        self._buf += data
        lines = []
        start = 0
        while True:
            end = self._buf.find(b"\n", start)
            if end < 0:
                break
            if end - start > self._limit:
                raise LineTooLong(end - start)
            lines.append(bytes(self._buf[start:end]))
            start = end + 1
        del self._buf[:start]
        if len(self._buf) > self._limit:
            raise LineTooLong(len(self._buf))
        return lines


def encode(msg: dict) -> bytes:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def decode(line: bytes) -> Any:
    """Eine Zeile als JSON (``ValueError`` bei kaputtem JSON, UTF-8 oder zu tiefer
    Verschachtelung)."""
    try:
        return json.loads(line.decode("utf-8"))
    except RecursionError:
        raise ValueError(tr("JSON zu tief verschachtelt")) from None


# --- Bedienelemente -----------------------------------------------------------------------

class RefError(ValueError):
    """Ungueltiges Bedienelement; ``message``/``params`` wie bei ``ApiError``."""

    def __init__(self, text: Any) -> None:
        self.message = N_("Bedienelement {ref!r} ungültig ({refs} oder wheel)")
        self.params = {"ref": text, "refs": REF_LIST}
        super().__init__(tr(self.message, **self.params))


def parse_ref(text: Any) -> ControlRef:
    """``"touch:3"`` -> ``ControlRef("touch", 3)``; ``"wheel"`` -> ``ControlRef("wheel", 0)``."""
    if not isinstance(text, str):
        raise RefError(text)
    kind, sep, index = text.strip().lower().partition(":")
    if kind == "wheel" and (not sep or index == "0"):
        return ControlRef("wheel", 0)
    count = REF_COUNTS.get(kind)
    if count is None or kind == "wheel" or not sep or not index.isdigit() or \
            int(index) >= count:
        raise RefError(text)
    return ControlRef(kind, int(index))


def format_ref(ref: ControlRef) -> str:
    return "wheel" if ref.kind == "wheel" else f"{ref.kind}:{ref.index}"


# --- Geraete-Ereignisse ---------------------------------------------------------------------

def event_from_dict(d: Any) -> Event:
    """``{"type": "button", "code": 7, "pressed": true}`` -> ``ButtonEvent(7, True)``.

    Felder wie in ``device.protocol``; ``type`` ist ``button``, ``rotate``, ``touch`` oder
    ``wheel_touch``. Fehlende, zusaetzliche oder falsch typisierte Felder: ``ValueError``.
    """
    if not isinstance(d, dict):
        raise ValueError(tr("Ereignis muss ein JSON-Objekt sein"))
    cls = EVENT_TYPES.get(d.get("type"))
    if cls is None:
        raise ValueError(tr("Unbekannter Ereignistyp {type!r} ({types})",
                            type=d.get("type"), types=", ".join(EVENT_TYPES)))
    names = [f.name for f in fields(cls)]
    extra = set(d) - set(names) - {"type"}
    if extra:
        raise ValueError(tr("Unbekannte Felder: {fields}", fields=", ".join(sorted(extra))))
    values = {}
    for f in fields(cls):
        if f.name not in d:
            raise ValueError(tr("Feld {field!r} fehlt", field=f.name))
        v = d[f.name]
        if f.type in (bool, "bool"):
            if not isinstance(v, bool):
                raise ValueError(tr("Feld {field!r} muss true oder false sein", field=f.name))
        elif not is_int(v):
            raise ValueError(tr("Feld {field!r} muss eine ganze Zahl sein", field=f.name))
        values[f.name] = v
    return cls(**values)


def event_to_dict(ev: Event) -> dict:
    return {"type": _EVENT_NAMES[type(ev)], **{f.name: getattr(ev, f.name) for f in fields(ev)}}
