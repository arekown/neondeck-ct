"""Profilformat aus einer Quelle: Feldbeschreibungen an den Dataclass-Feldern.

Jedes Feld des Profilmodells traegt als Metadatum eine ``Spec``. Aus ihnen entstehen
``to_json``, ``from_json`` und die Strukturpruefung (``validate``): ein neues Feld braucht
genau eine Zeile im Modell. ``from_json`` ist absichtlich nachsichtig (alte und handbearbeitete
Dateien laden, fehlende Felder bekommen den Dataclass-Standardwert); ``validate`` prueft
dagegen jeden Wert, den Engine und Zeichnen benutzen (Typ und Wertemenge).
"""
from __future__ import annotations

import dataclasses
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..core.i18n import N_, tr

log = logging.getLogger(__name__)

SPEC = "spec"  # Schluessel im ``metadata`` des Dataclass-Felds
FACTOR_RANGE = (1, 10)


def clamp_factor(v) -> int:
    """Drehfaktor als int, auf ``FACTOR_RANGE`` begrenzt (ungueltig -> 1)."""
    try:
        return max(FACTOR_RANGE[0], min(FACTOR_RANGE[1], int(v)))
    except (TypeError, ValueError, OverflowError):  # OverflowError: Infinity
        return 1


def is_color(text: str) -> bool:
    """Ob Pillow die Farbe kennt (``#rrggbb``, Namen, ``rgb(...)``)."""
    from PIL import ImageColor
    try:
        ImageColor.getrgb(text)
    except ValueError:
        return False
    return True


class Issues:
    """Sammelt die Fehlermeldungen einer Pruefung (deutsch, mit Pfad)."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    def expect(self, d: dict, key: str, path: str, types: tuple, what: str) -> bool:
        """``True``, wenn ``d[key]`` vorhanden ist und passt (dann weiter pruefen)."""
        if key not in d or (d[key] is None and type(None) in types):
            return False
        v = d[key]
        if isinstance(v, bool) and bool not in types or not isinstance(v, types):
            self.fail(f"{path}.{key}", tr("muss {what} sein", what=tr(what)))
            return False
        return True

    def obj(self, v, path: str) -> bool:
        if not isinstance(v, dict):
            self.fail(path, tr("muss ein Objekt sein"))
            return False
        return True


def _default(f: dataclasses.Field, empty):
    if f.default is not dataclasses.MISSING:
        return f.default
    if f.default_factory is not dataclasses.MISSING:
        return f.default_factory()
    return empty


@dataclass(frozen=True)
class Spec:
    """Ein Feld im Profil-JSON: laden, speichern, pruefen."""

    empty: Any = field(default=None, kw_only=True)  # Wert, wenn das Feld im JSON fehlt und kein Standardwert da ist

    def load(self, raw, default):
        return default if raw is _ABSENT else raw

    def dump(self, value):
        return value

    def check(self, c: Issues, d: dict, key: str, path: str) -> None:
        """Wert ``d[key]`` pruefen (``key`` ist vorhanden)."""


_ABSENT = object()


@dataclass(frozen=True)
class Text(Spec):
    nullable: bool = False
    choices: tuple[str, ...] = ()
    coerce: bool = False  # unbekannter Wert -> Standardwert (statt unveraendert laden)
    empty: Any = field(default="", kw_only=True)

    def load(self, raw, default):
        if raw is _ABSENT or (self.coerce and raw not in self.choices):
            return default
        return raw

    def check(self, c, d, key, path):
        types = (str, type(None)) if self.nullable else (str,)
        if c.expect(d, key, path, types, N_("Text oder null") if self.nullable else N_("Text")) \
                and self.choices and d[key] not in self.choices:
            c.fail(f"{path}.{key}", tr("muss {what} sein",
                                                what=f" {tr('oder')} ".join(self.choices)))


@dataclass(frozen=True)
class Color(Spec):
    nullable: bool = False

    def check(self, c, d, key, path):
        types = (str, type(None)) if self.nullable else (str,)
        if c.expect(d, key, path, types, N_("Farbe")) and d[key] is not None \
                and not is_color(d[key]):
            c.fail(f"{path}.{key}", tr("Farbe {value!r} unbekannt", value=d[key]))


@dataclass(frozen=True)
class Flag(Spec):
    empty: Any = field(default=False, kw_only=True)

    def load(self, raw, default):
        return default if raw is _ABSENT else bool(raw)

    def check(self, c, d, key, path):
        c.expect(d, key, path, (bool,), N_("true oder false"))


@dataclass(frozen=True)
class Whole(Spec):
    """Ganze Zahl oder null."""

    def check(self, c, d, key, path):
        c.expect(d, key, path, (int, type(None)), N_("eine ganze Zahl oder null"))


@dataclass(frozen=True)
class Factor(Spec):
    empty: Any = field(default=1, kw_only=True)

    def load(self, raw, default):
        return clamp_factor(default if raw is _ABSENT else raw)

    def check(self, c, d, key, path):
        v = d[key]
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                              or not math.isfinite(v)):
            c.fail(f"{path}.{key}", tr("muss eine Zahl sein"))


@dataclass(frozen=True)
class Action(Spec):
    """Aktion (``dict`` mit ``type``) oder null; ``required``: fehlend/leer -> ``{}``."""

    required: bool = False

    def load(self, raw, default):
        if self.required:
            return (default if raw is _ABSENT else raw) or {}
        return super().load(raw, default)

    def check(self, c, d, key, path):
        if c.expect(d, key, path, (dict, type(None)), N_("ein Objekt oder null")) \
                and d[key] is not None:
            c.expect(d[key], "type", f"{path}.{key}", (str, type(None)), N_("Text"))


@dataclass(frozen=True)
class Strings(Spec):
    def load(self, raw, default):
        return default if raw is _ABSENT else list(raw or [])

    def check(self, c, d, key, path):
        if c.expect(d, key, path, (list,), N_("eine Liste")) \
                and not all(isinstance(x, str) for x in d[key]):
            c.fail(f"{path}.{key}", tr("darf nur Texte enthalten"))


@dataclass(frozen=True)
class Part(Spec):
    """Verschachteltes Objekt einer ``Record``-Klasse; ``nullable``: leer -> ``None``."""

    cls: type = object
    nullable: bool = False

    def load(self, raw, default):
        if raw is _ABSENT or raw is None:
            return None if self.nullable else self.cls.from_json(None)
        return self.cls.from_json(raw) if raw or not self.nullable else None

    def dump(self, value):
        return None if value is None else value.to_json()

    def check(self, c, d, key, path):
        if c.expect(d, key, path, (dict, type(None)), N_("ein Objekt oder null")) \
                and d[key] is not None:
            check(self.cls, d[key], f"{path}.{key}", c)


@dataclass(frozen=True)
class Items(Spec):
    """Liste von Objekten; mit ``size`` auf diese Laenge gekuerzt/aufgefuellt."""

    cls: type = object
    size: int | None = None
    null_items: bool = False

    def load(self, raw, default):
        if raw is _ABSENT:
            raw = None
        items = list(raw or [])
        if self.size is not None:
            items = items[:self.size]
            items += [None] * (self.size - len(items))
        return [self.cls.from_json(x) for x in items]

    def dump(self, value):
        return [None if x is None else x.to_json() for x in value]

    def check(self, c, d, key, path):
        if not c.expect(d, key, path, (list, type(None)), N_("eine Liste")) or d[key] is None:
            return
        for i, item in enumerate(d[key]):
            here = f"{path}.{key}[{i}]"
            if item is None and self.null_items:
                continue
            if c.obj(item, here):
                check(self.cls, item, here, c)


def _code_ok(key, codes) -> bool:
    return isinstance(key, str) and key.isdecimal() and int(key) in codes


@dataclass(frozen=True)
class Keyed(Spec):
    """``{Tastencode: Belegung | null}`` fuer eine feste Menge von Codes (Tasten)."""

    cls: type = object
    codes: Any = ()

    def load(self, raw, default):
        raw = {} if raw is _ABSENT or raw is None else raw
        return {c: self.cls.from_json(raw.get(str(c))) for c in self.codes}

    def dump(self, value):
        return {str(c): None if value.get(c) is None else value[c].to_json()
                for c in self.codes}

    def check(self, c, d, key, path):
        if not c.expect(d, key, path, (dict, type(None)), N_("ein Objekt")) or d[key] is None:
            return
        for code, a in d[key].items():
            here = f"{path}.{key}.{code}"
            if not _code_ok(code, self.codes):
                c.fail(here, tr("Tastencode unbekannt"))
            elif a is not None and c.obj(a, here):
                check(self.cls, a, here, c)


@dataclass(frozen=True)
class Sticky(Keyed):
    """``{Tastennummer: Belegung}`` nur fuer belegte Tasten (Sticky-Felder)."""

    def load(self, raw, default):
        out = {}
        for k, v in ({} if raw is _ABSENT or raw is None else raw).items():
            try:
                code = int(k)
            except (TypeError, ValueError):
                code = None
            if code not in self.codes:  # wie beim Pruefen: nur Felder 0 .. 11
                log.warning("Workspace-Sticky: ungueltiger Tastencode %r uebersprungen", k)
                continue
            a = self.cls.from_json(v)
            if a is not None:
                out[code] = a
        return out

    def dump(self, value):
        return {str(c): a.to_json() for c, a in sorted(value.items())}


def prop(spec: Spec, default=dataclasses.MISSING, *, factory=dataclasses.MISSING,
         kw_only: bool = False):
    """Dataclass-Feld mit Beschreibung (``default``/``factory`` wie bei ``dataclasses.field``)."""
    kw: dict = {"metadata": {SPEC: spec}, "kw_only": kw_only}
    if factory is not dataclasses.MISSING:
        return field(default_factory=factory, **kw)
    if default is not dataclasses.MISSING:
        return field(default=default, **kw)
    return field(**kw)


def _specs(cls):
    return [(f, f.metadata[SPEC]) for f in dataclasses.fields(cls) if SPEC in f.metadata]


def dump(obj) -> dict:
    """Profil-JSON-Objekt (Schluessel in Feldreihenfolge)."""
    return {f.name: spec.dump(getattr(obj, f.name)) for f, spec in _specs(type(obj))}


def load(cls, d: dict | None) -> dict:
    """Konstruktorargumente aus JSON; fehlende Felder -> Standardwert."""
    d = d or {}
    return {f.name: spec.load(d.get(f.name, _ABSENT), _default(f, spec.empty))
            for f, spec in _specs(cls)}


def check(cls, d: dict, path: str, c: Issues) -> None:
    """Alle Felder von ``d`` gegen die Beschreibung von ``cls`` pruefen."""
    for f, spec in _specs(cls):
        if f.name in d:
            spec.check(c, d, f.name, path)


class Record:
    """Basis der Profil-Dataclasses: ``to_json``/``from_json`` aus den Feldbeschreibungen."""

    def to_json(self) -> dict:
        return dump(self)

    @classmethod
    def from_json(cls, d: dict | None):
        return cls(**load(cls, d))


def validate(cls, d, name: str) -> list[str]:
    """Fehler eines JSON-Objekts der Klasse ``cls`` (``name`` = Pfadanfang); leer = in Ordnung."""
    c = Issues()
    if c.obj(d, name):
        check(cls, d, name, c)
    return c.errors


PROFILE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")  # zugleich Dateiname
