"""Programmeinstellungen (``settings.json``) und Autostart-Eintrag."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import i18n, paths
from .fileio import read_json, write_atomic
from .i18n import N_, tr
from .paths import launcher_path
from .values import is_int, parse_view

log = logging.getLogger(__name__)

DEFAULT_PROFILE = "default"
DEFAULT_BRIGHTNESS = 8
BRIGHTNESS_MAX = 10
DEFAULT_THEME = "cockpit"
# Editor-Themes, Qt-frei (app.theme.THEMES hat dieselben Namen in derselben Reihenfolge)
THEME_NAMES = ("cockpit", "neutral", "system")
DISPLAY_SLEEP_MAX = 24 * 60  # Minuten
# Bildschirmschoner-Varianten (render.savers.SAVERS und „auto“; ein Test prueft das)
SAVER_NAMES = ("auto", "cockpit", "synthwave", "matrix", "warp", "aurora", "diashow")
# Geraete-Looks (render.look.LOOKS und „auto“; ein Test prueft das)
LOOK_NAMES = ("auto", "classic", "cockpit")
BRIGHTNESS_RANGE = range(BRIGHTNESS_MAX + 1)
SLEEP_MIN_RANGE = range(DISPLAY_SLEEP_MAX + 1)  # Displays schlafen nach (0 = nie)
SAVER_MIN_RANGE = SLEEP_MIN_RANGE                  # Bildschirmschoner nach (0 = aus)
SLIDE_S_RANGE = range(3, 3601)  # Diashow: Sekunden je Bild
DOUBLE_MS_RANGE = range(100, 1001)  # Doppeltipp-Fenster in ms
HOLD_MS_RANGE = range(200, 3001)    # Halten ab ms
# Ein/Aus-Einstellungen, die der Dienst nur merkt bzw. an den Tray gibt (API ``settings.put``)
FLAG_KEYS = ("notify_errors", "notify_connection", "notify_profile", "tray_mono",
             "first_run_done")


@dataclass(frozen=True)
class Field:
    """Typ und gueltige Werte einer Einstellung.

    ``kind``: ``bool``, ``int`` (``valid`` ist ein ``range``), ``choice`` (``valid`` ist ein
    Tupel, ``what`` benennt die Sache in der Fehlermeldung) oder ``str``."""

    kind: str
    valid: range | tuple | None = None
    what: str = ""


# Alle Einstellungen, die ``settings.put`` aendern darf (``last_pages`` merkt nur der Dienst)
FIELDS: dict[str, Field] = {
    "active_profile": Field("str"),
    "brightness": Field("int", BRIGHTNESS_RANGE),
    "autostart": Field("bool"),
    "theme": Field("choice", THEME_NAMES, N_("Theme")),
    "theme_scanlines": Field("bool"),
    # Sprache der Oberflaeche: ``auto`` oder ein Code aus ``data/i18n`` (wirkt nach Neustart)
    "language": Field("choice", (i18n.AUTO, *i18n.codes()), N_("Sprache")),
    "device_look": Field("choice", LOOK_NAMES, N_("Geräte-Look")),
    "dynamic_mode": Field("bool"),
    "display_sleep_min": Field("int", SLEEP_MIN_RANGE),
    "screensaver_min": Field("int", SAVER_MIN_RANGE),
    "screensaver": Field("choice", SAVER_NAMES, N_("Bildschirmschoner")),
    "screensaver_folder": Field("str"),
    "screensaver_slide_s": Field("int", SLIDE_S_RANGE),
    "lock_with_session": Field("bool"),
    "double_ms": Field("int", DOUBLE_MS_RANGE),
    "hold_ms": Field("int", HOLD_MS_RANGE),
    **{key: Field("bool") for key in FLAG_KEYS},
}


def validate_parts(key: str, value) -> tuple[str, dict] | None:
    """Wie ``validate``, aber als ``(Quelltext, params)`` fuer ``ApiError`` (der Client
    uebersetzt ``tr(Quelltext, **params)``); ``None``, wenn der Wert passt."""
    f = FIELDS.get(key)
    if f is None:
        return N_("Unbekannte Einstellung {key!r}"), {"key": key}
    if f.kind == "bool":
        return None if isinstance(value, bool) else (N_("{key} muss true oder false sein"),
                                                     {"key": key})
    if f.kind == "int":
        if not is_int(value):
            return N_("{key} muss eine ganze Zahl sein"), {"key": key}
        if value not in f.valid:
            return (N_("{key} muss {first}–{last} sein"),
                    {"key": key, "first": f.valid.start, "last": f.valid.stop - 1})
        return None
    if f.kind == "choice":
        if value not in f.valid:
            return (N_("{what} {value!r} gibt es nicht ({options})"),
                    {"what": tr(f.what), "value": value, "options": ", ".join(f.valid)})
        return None
    return None if isinstance(value, str) else (N_("{key} muss ein Text sein"), {"key": key})


def validate(key: str, value) -> str | None:
    """Fehlertext, wenn ``value`` fuer ``key`` nicht passt (Wortlaut der API), sonst None.

    Nur Typ und Bereich: ob ein Ordner oder ein Profil existiert, prueft der Dienst."""
    bad = validate_parts(key, value)
    return None if bad is None else tr(bad[0], **bad[1])


def _loaded(key: str, value) -> tuple[bool, object]:
    """``(uebernehmen, wert)`` fuer einen Wert aus der Datei. Wie ``validate``, aber
    nachsichtig: ``brightness`` wird geklemmt, ``active_profile``/``theme`` muessen nur nicht
    leerer Text sein (unbekannte Themes faengt ``theme.apply`` ab), ``screensaver_folder``
    wird nicht auf Existenz geprueft."""
    if key == "brightness":
        if not is_int(value):
            return False, None
        return True, max(0, min(BRIGHTNESS_MAX, value))
    if key in ("active_profile", "theme"):
        return isinstance(value, str) and bool(value), value
    return validate(key, value) is None, value


def settings_path() -> Path:
    return paths.config_dir() / "settings.json"


@dataclass
class Settings:
    active_profile: str = DEFAULT_PROFILE
    brightness: int = DEFAULT_BRIGHTNESS
    autostart: bool = False
    theme: str = DEFAULT_THEME
    theme_scanlines: bool = False
    language: str = i18n.AUTO  # ``auto``: Systemsprache; Dienst und Editor lesen sie beim Start
    device_look: str = "auto"  # LOOK_NAMES; auto: animiertes Cockpit zum Cockpit-Theme
    dynamic_mode: bool = True  # Profil folgt dem aktiven Fenster
    display_sleep_min: int = 0  # Displays nach so vielen Minuten ohne Eingabe schwarz (0 = aus)
    screensaver_min: int = 5    # Bildschirmschoner nach so vielen Minuten ohne Eingabe (0 = aus)
    screensaver: str = "auto"   # Variante (SAVER_NAMES); auto: passend zum Theme
    screensaver_folder: str = ""  # Diashow: Bilderordner (samt Unterordnern)
    screensaver_slide_s: int = 10  # Diashow: Sekunden je Bild
    lock_with_session: bool = True  # Bildschirmsperre sperrt auch das Geraet
    double_ms: int = 300  # Doppeltippen: Fenster nach dem ersten Loslassen
    hold_ms: int = 500    # Halten: ab so langer Druckdauer
    # Ruhe: Tray-Meldungen je Art abschaltbar, Tray-Symbol einfarbig
    notify_errors: bool = True       # Fehler (Profil kaputt, Grafiken fehlen …)
    notify_connection: bool = True   # Geraet getrennt / wieder verbunden
    notify_profile: bool = False     # Profilwechsel (Dynamic Mode wechselt oft)
    tray_mono: bool = False
    first_run_done: bool = False     # Ersteinrichtung im Editor gezeigt
    # zuletzt aktive Ansicht je Profil: {profil_id: {"workspace": str, "page": int}}
    last_pages: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> Settings:
        """Fehlende oder kaputte Datei/Werte -> Standardwerte (mit Log-Eintrag)."""
        path = settings_path()
        if not path.exists():
            return cls()
        try:
            data = read_json(path)
            if not isinstance(data, dict):
                raise ValueError("kein JSON-Objekt")
        except (OSError, ValueError) as e:
            log.error("Einstellungen %s nicht lesbar (%s); Standardwerte", path, e)
            return cls()
        s = cls()
        for key in FIELDS:
            if key in data:
                ok, value = _loaded(key, data[key])
                if ok:
                    setattr(s, key, value)
        s.last_pages = _last_pages(data.get("last_pages"))
        return s

    def save(self) -> None:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, json.dumps(asdict(self), ensure_ascii=False, indent=2))


def _last_pages(raw) -> dict:
    """Nur gueltige Eintraege ``{id: {"workspace": str, "page": int >= 0}}`` uebernehmen."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for pid, v in raw.items():
        view = parse_view(v, min_page=0)
        if view is not None:
            out[pid] = {"workspace": view[0], "page": view[1]}
    return out


# --- Autostart ----------------------------------------------------------------------

def autostart_path() -> Path:
    return paths.autostart_dir() / paths.AUTOSTART_FILE


def autostart_entry() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Neondeck CT\n"
        f"Comment={tr('Loupedeck CT unter Linux')}\n"
        f"Exec={launcher_path()}\n"
        "Icon=input-keyboard\n"
        "Terminal=false\n"
        "X-KDE-autostart-after=panel\n"
    )


def autostart_enabled() -> bool:
    return autostart_path().is_file()


def set_autostart(enabled: bool) -> None:
    """Schreibt bzw. entfernt den Autostart-Eintrag (wirft OSError bei Fehlern)."""
    path = autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(autostart_entry(), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
