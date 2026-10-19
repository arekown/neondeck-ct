"""Methodentabelle der API: Zeile lesen, Methode suchen, Parameter pruefen, antworten.

``Router.add`` sammelt die mit ``params.api_method`` gekennzeichneten Handler ein; jeder
Eintrag in ``methods`` ist danach ein Aufruf ``(verbindung, params) -> ergebnis`` (Tests
duerfen Eintraege ersetzen oder umhuellen). Fehler werden zur Fehlerantwort: ``ApiError``
mit Code und Text, alles andere als ``ERR_INTERNAL`` (mit Log).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.i18n import N_
from .params import checked
from .protocol import ERR_INTERNAL, ApiError, decode, encode, error_reply

log = logging.getLogger(__name__)

Handler = Callable[[Any, dict], Any]  # (Verbindung, params) -> Ergebnis | Later
UNGUARDED = ("ping",)  # beantwortet der Server auch, solange der Dienst noch startet


class Later:
    """Rueckgabe eines Handlers, dessen Antwort spaeter kommt (``finish`` im GUI-Thread)."""

    def __init__(self) -> None:
        self.on_done: Callable[[Any, str | None], None] | None = None

    def finish(self, result: Any, error: str | None = None) -> None:
        if self.on_done is not None:
            self.on_done(result, error)


def _bind(fn: Callable, specs: dict, with_conn: bool, raw: bool) -> Handler:
    def call(conn: Any, params: dict) -> Any:
        if raw:
            return fn(params)
        values = checked(specs, params)
        return fn(conn, **values) if with_conn else fn(**values)
    return call


class Router:
    """``send(verbindung, bytes)`` schickt Antworten; ``ready()`` sagt, ob der Dienst
    angebunden ist (sonst nur ``ping``)."""

    def __init__(self, send: Callable[[Any, bytes], None], ready: Callable[[], bool]) -> None:
        self._send = send
        self._ready = ready
        self.methods: dict[str, Handler] = {}

    def add(self, *handlers: object) -> None:
        """Alle API-Methoden der Objekte ``handlers`` eintragen."""
        for obj in handlers:
            for cls in reversed(type(obj).__mro__):
                for attr, fn in vars(cls).items():
                    meta = getattr(fn, "api_method", None)
                    if meta is not None:
                        name, specs, with_conn, raw = meta
                        self.methods[name] = _bind(getattr(obj, attr), specs, with_conn, raw)

    def handle_line(self, conn: Any, line: bytes) -> None:
        msg = _message(line)
        if msg is None:
            return
        rid, wants_reply = msg.get("id"), "id" in msg
        try:
            result = self._call(conn, msg)
            if isinstance(result, Later):
                if wants_reply:
                    result.on_done = lambda res, err: self._send(conn, encode(
                        error_reply(rid, err) if err else {"id": rid, "result": res}))
                return
            reply = encode({"id": rid, "result": result})
        except ApiError as e:
            reply = encode(error_reply(rid, e))
        except Exception as e:
            log.exception("API: %s fehlgeschlagen", msg.get("method"))
            reply = encode(error_reply(rid, ApiError(ERR_INTERNAL, N_("Interner Fehler: {error}"),
                                                          {"error": str(e)})))
        if wants_reply:
            self._send(conn, reply)

    def _call(self, conn: Any, msg: dict) -> Any:
        method = msg.get("method")
        params = msg.get("params")
        params = {} if params is None else params
        if not isinstance(method, str):
            raise ApiError("request.no_method", N_("Anfrage ohne Methode"))
        if not isinstance(params, dict):
            raise ApiError("request.bad_params", N_("params muss ein JSON-Objekt sein"))
        handler = self.methods.get(method)
        if handler is None:
            raise ApiError("request.unknown_method", N_("Unbekannte Methode {method!r}"),
                           {"method": method})
        if method not in UNGUARDED and not self._ready():
            raise ApiError("service.starting", N_("Dienst startet noch"))
        return handler(conn, params)


def _message(line: bytes) -> dict | None:
    """Eine Anfragezeile als JSON-Objekt; Leeres und Kaputtes wird (mit Log) uebergangen."""
    if not line.strip():
        return None
    try:
        msg = decode(line)
    except Exception as e:  # noqa: BLE001 - kaputtes JSON, UTF-8, Verschachtelung …
        log.warning("API: kaputte Zeile ignoriert (%s)", e)
        return None
    if not isinstance(msg, dict):
        log.warning("API: Nachricht ist kein JSON-Objekt – ignoriert")
        return None
    return msg
