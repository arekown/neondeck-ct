"""Mehrsprachigkeit ohne Qt: Deutsch ist der Quelltext, je weitere Sprache eine JSON-Datei.

Im Code stehen die deutschen Texte in ``tr("…")`` (wie die msgid bei gettext). Jede weitere
Sprache ist genau eine Datei ``data/i18n/<code>.json``::

    {"_meta": {"name": "English", "code": "en"},
     "Profil {name} geladen": "Profile {name} loaded"}

Fehlt ein Eintrag oder ist er leer, bleibt der deutsche Text. Platzhalter ``{name}`` fuellt
``tr(text, name=…)`` per ``str.format``; ein fehlender Platzhalter bleibt stehen, statt
abzustuerzen. Texte, die schon beim Import entstehen (Tabellen, ``@register(label=…)``,
``Param(…)``, ``Field.what``), markiert ``N_("…")`` nur fuer ``tools/i18n.py``; uebersetzt
wird beim Anzeigen mit ``tr(wert)``.

Die Sprache setzt jeder Prozess einmal beim Start (``set_language``); ``auto`` nimmt die
Systemsprache (``LC_ALL``, ``LC_MESSAGES``, ``LANG``), wenn es eine Datei dafuer gibt.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .fileio import read_json

log = logging.getLogger(__name__)

SOURCE = "de"          # Sprache des Quelltexts (braucht keine Datei)
SOURCE_NAME = "Deutsch"
AUTO = "auto"          # Einstellung: Systemsprache
META = "_meta"         # Schluessel fuer Name und Code in der Sprachdatei


@dataclass
class _Catalog:
    code: str = SOURCE
    texts: dict[str, str] = field(default_factory=dict)


_current = _Catalog()  # ``texts`` wird nur als Ganzes ersetzt (Lesen aus Threads ist sicher)


class _KeepMissing(dict):
    """Platzhalter ohne Wert bleiben als ``{name}`` stehen."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def i18n_dir() -> Path:
    """Ordner der Sprachdateien (mitgeliefert, ``data/i18n``)."""
    return paths.bundled_dir() / "i18n"


def N_(text: str) -> str:
    """Text fuer die Uebersetzung markieren, ohne ihn zu uebersetzen (Importzeit)."""
    return text


def format_text(text: str, params: dict) -> str:
    """``text.format(**params)``; bei kaputten Platzhaltern unveraendert ``text``."""
    if not params:
        return text
    try:
        return text.format_map(_KeepMissing(params))
    except (ValueError, IndexError, KeyError, AttributeError, TypeError):
        return text


def tr(text: str, /, **params: object) -> str:
    """Uebersetzung von ``text`` (deutscher Quelltext) in der eingestellten Sprache, mit
    ``params`` gefuellt; ohne Eintrag der deutsche Text."""
    return format_text(_current.texts.get(text) or text, params)


def language() -> str:
    """Code der eingestellten Sprache (``de``, ``en`` …)."""
    return _current.code


def _files() -> dict[str, Path]:
    folder = i18n_dir()
    if not folder.is_dir():
        return {}
    return {p.stem: p for p in sorted(folder.glob("*.json")) if p.stem != SOURCE}


def _load(path: Path) -> dict | None:
    try:
        data = read_json(path)
    except (OSError, ValueError) as e:
        log.warning("Sprachdatei %s nicht lesbar: %s", path, e)
        return None
    if not isinstance(data, dict):
        log.warning("Sprachdatei %s ist kein JSON-Objekt", path)
        return None
    return data


def available() -> list[tuple[str, str]]:
    """``[(code, name)]``: Deutsch und jede lesbare Datei in ``data/i18n``."""
    out = [(SOURCE, SOURCE_NAME)]
    for code, path in _files().items():
        data = _load(path)
        if data is None:
            continue
        meta = data.get(META)
        name = meta.get("name") if isinstance(meta, dict) else None
        out.append((code, name if isinstance(name, str) and name else code))
    return out


def codes() -> tuple[str, ...]:
    """Codes aller Sprachen (Deutsch zuerst), ohne die Dateien zu lesen."""
    return (SOURCE, *_files())


def system_language() -> str:
    """Sprachcode aus ``LC_ALL``, ``LC_MESSAGES`` oder ``LANG`` (``de_DE.UTF-8`` -> ``de``);
    leer, wenn nichts gesetzt ist (oder ``C``/``POSIX``)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            code = value.split(".")[0].split("@")[0].split("_")[0].lower()
            return "" if code in ("c", "posix") else code
    return ""


def resolve(setting: str) -> str:
    """Einstellung (``auto`` oder Code) -> Code einer vorhandenen Sprache, sonst Deutsch."""
    code = system_language() if setting == AUTO else setting
    return code if code in codes() else SOURCE


def set_language(setting: str) -> str:
    """Sprache einstellen (``auto`` oder Code) und ihre Datei laden; liefert den Code, der
    jetzt gilt. Unbekannte Sprache oder kaputte Datei: Deutsch."""
    code = resolve(setting)
    data = _load(_files()[code]) if code != SOURCE else {}
    if data is None:
        code, data = SOURCE, {}
    texts = {k: v for k, v in data.items()
             if k != META and isinstance(k, str) and isinstance(v, str) and v}
    _current.code, _current.texts = code, texts
    return code
