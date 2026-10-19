"""Deklarative Pruefung der Anfrage-Parameter (eine Stelle fuer alle API-Methoden).

Jede Methode nennt ihre Parameter mit einer *Regel* (``Spec``), z. B.
``@api_method("versions.get", id=ProfileId(), name=Text("name fehlt"))``. Der Router
prueft vor dem Aufruf alle Regeln der Reihe nach; der Handler bekommt nur noch gepruefte
Werte als Schluesselwortargumente. Fehler sind ``ApiError`` mit Code und Text wie bisher.

Fehlt ein Parameter, gilt ``default`` (ohne Pruefung, ``UNSET`` = „nicht angegeben“); steht
er da, wird er geprueft – ``null`` auch, ausser bei ``nullable`` (dann wie fehlend).
Pflichtparameter (``required=True``) werden immer geprueft, ein fehlender als ``None``.
Unbekannte Parameter werden ignoriert.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.i18n import N_
from ..core.settings import validate_parts as validate_setting
from ..core.values import is_int
from ..device.layout import ControlRef
from ..profile.model import PROFILE_ID_RE
from .protocol import ApiError, RefError, event_from_dict, parse_ref

UNSET: Any = object()  # Standardwert „nicht angegeben“ (von ``null`` unterscheidbar)


@dataclass(frozen=True)
class Spec:
    """Regel fuer einen Parameter: ``check(name, wert) -> geprueft`` oder ``ApiError``."""

    required: bool = False
    default: Any = None
    nullable: bool = False

    def value(self, name: str, params: dict) -> Any:
        absent = name not in params or (self.nullable and params[name] is None)
        if absent and not self.required:
            return self.default
        return self.check(name, params.get(name))

    def check(self, name: str, value: Any) -> Any:
        return value


@dataclass(frozen=True)
class Int(Spec):
    """Ganze Zahl (kein ``bool``); ``minimum`` mit eigenem Fehler ``param.negative``."""

    minimum: int | None = None

    def check(self, name: str, value: Any) -> Any:
        if not is_int(value):
            raise ApiError("param.not_int", N_("{name} muss eine ganze Zahl sein"), {"name": name})
        if self.minimum is not None and value < self.minimum:
            raise ApiError("param.negative", N_("{name} darf nicht negativ sein"), {"name": name})
        return value


@dataclass(frozen=True)
class Text(Spec):
    """Nicht leerer Text; ``strip``: ohne Leerraum am Rand (und nicht nur Leerraum)."""

    missing: str = ""  # Fehlertext („Name fehlt“)
    strip: bool = False
    required: bool = True

    def check(self, name: str, value: Any) -> Any:
        if isinstance(value, str) and self.strip:
            value = value.strip()
        if not isinstance(value, str) or not value:
            raise ApiError("param.missing", self.missing or N_("{name} fehlt"), {"name": name})
        return value


@dataclass(frozen=True)
class Choice(Spec):
    """Einer von ``options``; ``message`` ist der Fehlertext."""

    options: tuple = ()
    message: str = ""

    def check(self, name: str, value: Any) -> Any:
        if value not in self.options:
            raise ApiError("param.bad_choice", self.message,
                           {"name": name, "options": ", ".join(map(str, self.options))})
        return value


@dataclass(frozen=True)
class Obj(Spec):
    """JSON-Objekt (``dict``); ``with_type``: mit nicht leerem Text ``type`` (Aktion)."""

    message: str = ""
    with_type: bool = False

    def check(self, name: str, value: Any) -> Any:
        if not isinstance(value, dict) or (self.with_type and not (
                isinstance(value.get("type"), str) and value["type"])):
            raise ApiError("request.bad_params", self.message)
        return value


@dataclass(frozen=True)
class ProfileId(Spec):
    """Profil-Kennung im gueltigen Format (ob es das Profil gibt, prueft der Handler)."""

    required: bool = True

    def check(self, name: str, value: Any) -> Any:
        if not isinstance(value, str) or not PROFILE_ID_RE.fullmatch(value):
            raise ApiError("profile.bad_id", N_("Profil-Kennung {id!r} ungültig"), {"id": value})
        return value


@dataclass(frozen=True)
class Ref(Spec):
    """Bedienelement ``"touch:3"``/``"wheel"`` als ``ControlRef``; ``only``: nur diese Art
    (sonst ``only_code``/``only_message``)."""

    required: bool = True
    only: str = ""
    only_code: str = ""
    only_message: str = ""

    def check(self, name: str, value: Any) -> ControlRef:
        try:
            ref = parse_ref(value)
        except RefError as e:
            raise ApiError("param.bad_ref", e.message, e.params) from None
        if self.only and ref.kind != self.only:
            raise ApiError(self.only_code, self.only_message)
        return ref


@dataclass(frozen=True)
class AbsPath(Spec):
    """Absoluter Pfad; ``null``/leer bedeutet „keiner“ (``None``)."""

    def check(self, name: str, value: Any) -> Any:
        if value in (None, ""):
            return None
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ApiError("param.not_absolute", N_("{name} muss ein absoluter Pfad sein"),
                           {"name": name})
        return value


@dataclass(frozen=True)
class Event(Spec):
    """Geraete-Ereignis (``protocol.event_from_dict``)."""

    required: bool = True

    def check(self, name: str, value: Any) -> Any:
        try:
            return event_from_dict(value)
        except ValueError as e:
            raise ApiError("event.invalid", N_("Ereignis ungültig: {reason}"), {"reason": str(e)}) from None


@dataclass(frozen=True)
class Setting(Spec):
    """Wert einer Einstellung (Typ und Bereich aus ``core.settings``); ``null`` = keiner."""

    key: str = ""

    def check(self, name: str, value: Any) -> Any:
        bad = None if value is None else validate_setting(self.key or name, value)
        if bad is not None:
            raise ApiError("settings.invalid", bad[0], bad[1])
        return value


def checked(specs: dict[str, Spec], params: dict) -> dict[str, Any]:
    """Alle Regeln der Reihe nach anwenden; gepruefte Werte je Name."""
    return {name: spec.value(name, params) for name, spec in specs.items()}


def api_method(method: str, /, *, with_conn: bool = False, raw: bool = False,
               **specs: Spec) -> Callable[[Callable], Callable]:
    """Handler als API-Methode ``method`` kennzeichnen (``Router.add`` sammelt sie ein).

    ``with_conn``: der Handler bekommt zuerst die Verbindung; ``raw``: er bekommt alle
    Parameter ungeprueft als ein ``dict`` (``settings.put`` prueft gegen das
    Einstellungsschema)."""
    def deco(fn: Callable) -> Callable:
        fn.api_method = (method, specs, with_conn, raw)
        return fn
    return deco
