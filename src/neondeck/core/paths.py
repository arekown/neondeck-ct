"""Datenorte; mit Umgebungsvariable NEONDECK_HOME umbiegbar (Tests)."""
import os
import shutil
from pathlib import Path

APP_ID = "neondeck-ct"                      # Ordner-, Starter- und Desktop-Name
AUTOSTART_FILE = f"{APP_ID}.desktop"
LEGACY_ID = "loupedeck-linux"               # Name bis zur Umbenennung (Uebernahme beim Start)
LEGACY_AUTOSTART_FILE = f"{LEGACY_ID}.desktop"


def _home_override() -> Path | None:
    v = os.environ.get("NEONDECK_HOME")
    return Path(v) if v else None


def _xdg(var: str, fallback: str) -> Path:
    """XDG-Basisordner aus ``var`` (nur absolute Pfade zaehlen), sonst ``~/<fallback>``."""
    v = os.environ.get(var, "")
    return Path(v) if v and Path(v).is_absolute() else Path.home() / fallback


def xdg_config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def xdg_data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def xdg_state_home() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def runtime_dir() -> Path | None:
    """Laufzeitordner des Benutzers (``$XDG_RUNTIME_DIR``), ``None``, wenn es ihn nicht gibt."""
    v = os.environ.get("XDG_RUNTIME_DIR", "")
    return Path(v) if v and Path(v).is_dir() else None


def config_dir() -> Path:
    h = _home_override()
    return h / "config" if h else xdg_config_home() / APP_ID


def data_dir() -> Path:
    h = _home_override()
    return h / "share" if h else xdg_data_home() / APP_ID


def state_dir() -> Path:
    h = _home_override()
    return h / "state" if h else xdg_state_home() / APP_ID


def autostart_dir() -> Path:
    h = _home_override()
    return h / "autostart" if h else xdg_config_home() / "autostart"


def bundled_dir() -> Path:
    """Mitgelieferte Dateien im Repo (``data/``), nur lesend; nicht umbiegbar."""
    return Path(__file__).resolve().parents[3] / "data"


def fonts_dir() -> Path:
    return bundled_dir() / "fonts"


def launcher_path() -> Path:
    """Startskript, das tools/install.sh anlegt."""
    return Path.home() / ".local" / "bin" / APP_ID


def migrate_legacy(autostart_entry: str) -> list[str]:
    """Einmalige Uebernahme aus der Zeit vor der Umbenennung (Dienst und Editor beim Start,
    vor dem ersten Schreiben in die Datenorte).

    Gibt es einen neuen Ordner (config, share, state) noch nicht, aber den alten
    ``loupedeck-linux``, wird der alte verschoben. Ein alter Autostart-Eintrag wird durch
    ``autostart_entry`` unter dem neuen Namen ersetzt. Mit ``NEONDECK_HOME`` gibt es nichts
    zu uebernehmen. Liefert Zeilen fuers Log (das erst danach startet); wirft nie.
    """
    if _home_override():
        return []
    notes = []
    try:
        for base in (xdg_config_home(), xdg_data_home(), xdg_state_home()):
            old, new = base / LEGACY_ID, base / APP_ID
            if old.is_dir() and not new.exists():
                shutil.move(old, new)
                notes.append(f"Übernommen: {old} -> {new}")
        old_auto = autostart_dir() / LEGACY_AUTOSTART_FILE
        if old_auto.is_file():
            new_auto = autostart_dir() / AUTOSTART_FILE
            new_auto.write_text(autostart_entry, encoding="utf-8")
            old_auto.unlink()
            notes.append(f"Autostart ersetzt: {old_auto} -> {new_auto}")
    except OSError as e:
        notes.append(f"Übernahme der alten Datenorte fehlgeschlagen: {e}")
    return notes
