"""Installierte Anwendungen aus ``.desktop``-Dateien (App-Auswahl fuer Profile, „App starten“).

Gelesen werden die Benutzer-, Flatpak-, Snap- und Systemordner (``XDG_DATA_HOME``,
``XDG_DATA_DIRS`` und feste Ersatzorte); eine Datei weiter vorn in der Suchreihenfolge
ueberdeckt gleichnamige weiter hinten (auch ``Hidden``/``NoDisplay``).
Beachtet werden ``NoDisplay``, ``Hidden``, ``OnlyShowIn``/``NotShowIn`` (aktuelle
Arbeitsumgebung, Standard KDE) und ``TryExec``.
"""
from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

ENTRY_GROUP = "[Desktop Entry]"
DEFAULT_DATA_DIRS = "/usr/local/share:/usr/share"
DEFAULT_DESKTOPS = ("KDE",)
# Feste Ersatzorte, falls XDG_DATA_DIRS sie nicht nennt (z. B. Dienst aus systemd ohne Umgebung)
FALLBACK_DIRS = ("/var/lib/flatpak/exports/share/applications",
                 "/var/lib/snapd/desktop/applications",
                 "/usr/local/share/applications",
                 "/usr/share/applications")
_ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


@dataclass(frozen=True)
class DesktopApp:
    id: str        # Desktop-Datei-Kennung (Dateiname ohne .desktop; Unterordner mit "-")
    name: str      # Anzeigename (deutsch, wenn vorhanden)
    icon: str      # Symbolname oder Pfad
    wm_class: str  # StartupWMClass (leer, wenn nicht angegeben)
    exec: str      # Exec-Zeile (Escape-Folgen aufgeloest, Feldcodes wie %U bleiben)


def default_dirs() -> list[Path]:
    """Suchreihenfolge: Benutzer, Benutzer-Flatpak, ``XDG_DATA_DIRS``, Ersatzorte."""
    data_home = paths.xdg_data_home()
    dirs = [data_home / "applications", data_home / "flatpak/exports/share/applications"]
    data_dirs = os.environ.get("XDG_DATA_DIRS") or DEFAULT_DATA_DIRS
    dirs += [Path(d) / "applications" for d in data_dirs.split(":") if d]
    dirs += [Path(d) for d in FALLBACK_DIRS]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _languages() -> list[str]:
    """Locale-Schluessel fuer ``Name[..]``, genauester zuerst (z. B. de_DE, de)."""
    lang = ""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        lang = os.environ.get(var, "")
        if lang:
            break
    lang = lang.split(".")[0].split("@")[0]
    if not lang or lang in ("C", "POSIX"):
        return []
    short = lang.split("_")[0]
    return [lang, short] if short != lang else [lang]


def _desktops() -> list[str]:
    raw = os.environ.get("XDG_CURRENT_DESKTOP", "")
    names = [d for d in raw.split(":") if d]
    return names or list(DEFAULT_DESKTOPS)


def _unescape(value: str) -> str:
    """Escape-Folgen der Desktop-Entry-Spezifikation (\\s \\n \\t \\r \\\\)."""
    if "\\" not in value:
        return value
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value) and value[i + 1] in _ESCAPES:
            out.append(_ESCAPES[value[i + 1]])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _list(value: str) -> list[str]:
    return [v for v in value.split(";") if v]


def _read_entry(path: Path) -> dict[str, str] | None:
    """Schluessel der Gruppe ``[Desktop Entry]``; ``None``, wenn nicht lesbar."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        log.debug("%s nicht lesbar: %s", path, e)
        return None
    entry: dict[str, str] = {}
    in_entry = found = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            in_entry = line == ENTRY_GROUP
            found = found or in_entry
            continue
        if in_entry and "=" in line:
            key, value = line.split("=", 1)
            entry.setdefault(key.strip(), _unescape(value.strip()))
    return entry if found else None


def _localized(entry: dict[str, str], key: str, langs: list[str]) -> str:
    """``key[lang]`` in der ersten passenden Sprache, sonst ``key`` (leer ohne)."""
    return next((entry[f"{key}[{lang}]"] for lang in langs if f"{key}[{lang}]" in entry),
                entry.get(key, ""))


def describe_file(path: Path) -> tuple[str, str] | None:
    """Name (in der Sprache der Sitzung) und ``Icon`` einer beliebigen ``.desktop``-Datei,
    auch ausserhalb der Anwendungsordner (z. B. Verknuepfungen auf dem Schreibtisch)."""
    entry = _read_entry(path)
    if entry is None:
        return None
    name = _localized(entry, "Name", _languages()) or path.stem
    return name, entry.get("Icon", "")


def _try_exec_ok(value: str) -> bool:
    if not value:
        return True
    if Path(value).is_absolute():
        return os.access(value, os.X_OK)
    return shutil.which(value) is not None


def _app(app_id: str, entry: dict[str, str], langs: list[str],
         desktops: list[str]) -> DesktopApp | None:
    if entry.get("Type", "Application") != "Application":
        return None
    if entry.get("NoDisplay", "").lower() == "true" or entry.get("Hidden", "").lower() == "true":
        return None
    only = _list(entry.get("OnlyShowIn", ""))
    if only and not any(d in only for d in desktops):
        return None
    if any(d in _list(entry.get("NotShowIn", "")) for d in desktops):
        return None
    if not _try_exec_ok(entry.get("TryExec", "")):
        return None
    name = _localized(entry, "Name", langs)
    if not name:
        return None
    return DesktopApp(app_id, name, entry.get("Icon", ""), entry.get("StartupWMClass", ""),
                      entry.get("Exec", ""))


def list_apps(dirs: Iterable[Path] | None = None) -> list[DesktopApp]:
    """Sichtbare Anwendungen, nach Namen sortiert (liest Dateien: nicht im GUI-Thread)."""
    langs, desktops = _languages(), _desktops()
    seen: set[str] = set()
    apps: list[DesktopApp] = []
    for base_dir in (default_dirs() if dirs is None else dirs):
        base = Path(base_dir)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.desktop")):
            app_id = str(path.relative_to(base).with_suffix("")).replace(os.sep, "-")
            if app_id in seen:
                continue
            entry = _read_entry(path)
            if entry is None:
                continue
            seen.add(app_id)  # auch ausgeblendete Eintraege ueberdecken spaetere
            app = _app(app_id, entry, langs, desktops)
            if app is not None:
                apps.append(app)
    return sorted(apps, key=lambda a: (a.name.casefold(), a.id))


def find_desktop_file(app_id: str, dirs: Iterable[Path] | None = None) -> Path | None:
    """Die ``.desktop``-Datei zur Kennung ``app_id`` (erste in der Suchreihenfolge); ein
    ``-`` der Kennung kann fuer einen Unterordner stehen (``kde-kate`` -> ``kde/kate``)."""
    if not app_id or "/" in app_id or "\\" in app_id or app_id.startswith("."):
        return None
    parts = app_id.split("-")
    if any(part in ("", ".", "..") for part in parts):
        return None
    for base in (default_dirs() if dirs is None else dirs):
        root = Path(base).resolve()
        for i in range(len(parts)):
            path = Path(base, *parts[:i], "-".join(parts[i:]) + ".desktop")
            if path.is_file() and path.resolve().is_relative_to(root):
                return path
    return None
