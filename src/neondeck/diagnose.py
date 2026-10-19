"""Einrichtung pruefen: Sitzung, Geraet, Rechte, Hilfsprogramme, Dienst (Editor-Seite „Diagnose“).

``run_checks`` liefert je Pruefung gruen/rot, eine Erklaerung und – wo es eine gibt – einen
kopierbaren Reparaturbefehl. Das Programm fuehrt diese Befehle nie selbst aus (kein ``sudo``).

Was nur der laufende Dienst weiss (Geraet verbunden, Firmware, KWin-Skript, Sitzungswaechter,
Socket), kommt als ``service`` aus der API-Methode ``diag``; ohne Dienst (``None``) melden
diese Pruefungen „Dienst nicht erreichbar“. Alles Lokale liest ``Env`` (Tests geben eine
Ersatz-Umgebung).
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .api.protocol import socket_path
from .core import paths
from .core.i18n import N_, tr
from .core.proc import PACTL, SETPRIV, WL_COPY
from .device.discovery import PRODUCT_IDS, VENDOR_ID, list_cts

UDEV_RULES_PATH = "/etc/udev/rules.d/70-neondeck-ct.rules"
UDEV_RULES = (
    'SUBSYSTEM=="tty", ACTION=="add", ATTRS{idVendor}=="2ec2", '
    'ATTRS{idProduct}=="0003|0007", MODE="0660", TAG+="uaccess"\n'
    'KERNEL=="uinput", SUBSYSTEM=="misc", ACTION=="add", TAG+="uaccess", '
    'OPTIONS+="static_node=uinput"\n'
)
REPO = Path(__file__).resolve().parents[2]
NO_SERVICE = N_("Dienst nicht erreichbar")

# Paketnamen je Paketverwaltung: (dnf, apt, pacman)
_PACKAGES = {
    WL_COPY: ("wl-clipboard", "wl-clipboard", "wl-clipboard"),
    PACTL: ("pulseaudio-utils", "pulseaudio-utils", "libpulse"),
    SETPRIV: ("util-linux-core", "util-linux", "util-linux"),
}
_MANAGERS = (("dnf", "sudo dnf install {}"), ("apt", "sudo apt install {}"),
             ("pacman", "sudo pacman -S {}"))


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    ok: bool
    detail: str = ""
    fix: str | None = None  # kopierbarer Befehl (wird nie selbst ausgefuehrt)


@dataclass
class Env:
    """Was die lokalen Pruefungen lesen (Standard: das echte System)."""
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    tty_root: str = "/sys/class/tty"
    uinput: str = "/dev/uinput"
    which: Callable[[str], str | None] = shutil.which
    access: Callable[[str, int], bool] = os.access
    data_dirs: list[Path] | None = None   # Standard: config, share, state
    fonts: dict[str, Path] | None = None  # Standard: render.fonts.font_files()
    assets_manifest: Path | None = None   # Standard: assets_dir()/manifest.json
    socket: str | None = None             # Standard: protocol.socket_path()


def udev_fix() -> str:
    """Befehle, die die udev-Regel anlegen und anwenden (zum Kopieren)."""
    return (f"sudo tee {UDEV_RULES_PATH} > /dev/null <<'EOF'\n{UDEV_RULES}EOF\n"
            "sudo udevadm control --reload-rules && sudo udevadm trigger")


def _install(tool: str, which: Callable[[str], str | None]) -> str:
    names = _PACKAGES[tool]
    for (manager, cmd), pkg in zip(_MANAGERS, names):
        if which(manager):
            return cmd.format(pkg)
    return _MANAGERS[0][1].format(names[0])


def _writable_dir(d: Path, access) -> bool:
    """Ordner beschreibbar oder (fehlt er) anlegbar."""
    p = d
    while not p.exists():
        if p.parent == p:
            return False
        p = p.parent
    return p.is_dir() and access(str(p), os.W_OK | os.X_OK)


def run_checks(service: dict | None = None, env: Env | None = None) -> list[Check]:
    env = env or Env()
    sv = service if isinstance(service, dict) else None
    return [
        _session(env), *_device(env, sv), _uinput(env), _firmware(sv),
        _kwin(sv), _dbus(sv), _session_watcher(sv),
        *(_tool(env, t, label) for t, label in (
            (WL_COPY, tr("wl-copy vorhanden (Text über die Zwischenablage einfügen)")),
            (PACTL, tr("pactl vorhanden (Lautstärke, Stumm-Zustand, Mixer)")),
            (SETPRIV, tr("setpriv vorhanden (gestartete Befehle enden mit dem Dienst)")))),
        _service(env, sv), _data_dirs(env), _fonts(env), _assets(env),
    ]


# --- einzelne Pruefungen ------------------------------------------------------------------

def _session(env: Env) -> Check:
    kind = env.environ.get("XDG_SESSION_TYPE", "")
    desktop = env.environ.get("XDG_CURRENT_DESKTOP", "")
    ok = kind == "wayland" and "KDE" in desktop.split(":")
    unknown = tr("unbekannt")
    detail = tr("Sitzungstyp „{kind}“, Desktop „{desktop}“", kind=kind or unknown,
                desktop=desktop or unknown)
    if not ok:
        detail += tr(" – Dynamic Mode und KDE-Funktionen brauchen KDE Plasma unter Wayland")
    return Check("session", tr("Sitzung: Wayland mit KDE Plasma"), ok, detail)


def _device(env: Env, sv: dict | None) -> list[Check]:
    found = list_cts(env.tty_root)
    ids = "/".join(f"{VENDOR_ID}:{p}" for p in PRODUCT_IDS)
    if found:
        detail = ", ".join(f"{port} ({VENDOR_ID}:{product})" for port, product in found)
        if sv is not None:
            detail += " – " + (tr("verbunden (Seriennummer {serial})",
                                  serial=sv.get("serial") or tr("unbekannt"))
                               if sv.get("connected") else tr("Dienst ist nicht verbunden"))
        device = Check("device", tr("Loupedeck CT gefunden ({ids})", ids=ids), True, detail)
    else:
        device = Check("device", tr("Loupedeck CT gefunden ({ids})", ids=ids), False,
                       tr("Kein CT am USB gefunden – Kabel und Anschluss prüfen"))
    if not found:
        access = Check("tty_access", tr("Zugriff auf das Gerät (/dev/ttyACM*)"), False,
                       tr("Nicht prüfbar, solange kein Gerät angeschlossen ist"))
    else:
        denied = [port for port, _ in found if not env.access(port, os.R_OK | os.W_OK)]
        access = Check("tty_access", tr("Zugriff auf das Gerät (/dev/ttyACM*)"), not denied,
                       tr("Lesen und Schreiben erlaubt") if not denied else
                       tr("Kein Zugriff auf {ports} – udev-Regel anlegen (oder Benutzer in die "
                          "Gruppe „dialout“), dann Gerät neu anstecken", ports=", ".join(denied)),
                       None if not denied else udev_fix())
    return [device, access]


def _uinput(env: Env) -> Check:
    label = tr("/dev/uinput beschreibbar (Tastenkürzel, Texteingabe)")
    if not Path(env.uinput).exists():
        return Check("uinput", label, False, tr("{path} fehlt – Kernelmodul uinput laden", path=env.uinput),
                     "sudo modprobe uinput\n" + udev_fix())
    if not env.access(env.uinput, os.W_OK):
        return Check("uinput", label, False,
                     tr("Kein Schreibrecht auf {path} – udev-Regel anlegen, dann neu anmelden",
                        path=env.uinput), udev_fix())
    return Check("uinput", label, True, tr("{path} ist beschreibbar", path=env.uinput))


def _firmware(sv: dict | None) -> Check:
    label = tr("Firmware-Version des Geräts")
    if sv is None:
        return Check("firmware", label, False, tr(NO_SERVICE))
    if not sv.get("connected"):
        return Check("firmware", label, False, tr("Gerät nicht verbunden"))
    fw = sv.get("firmware")
    return Check("firmware", label, bool(fw),
                 tr("Firmware {version} (nur gelesen, nie verändert)", version=fw) if fw else
                 tr("Das Gerät hat keine Firmware-Version gemeldet"))


def _kwin(sv: dict | None) -> Check:
    label = tr("KWin-Skript geladen (Dynamic Mode)")
    if sv is None:
        return Check("kwin_script", label, False, tr(NO_SERVICE))
    if sv.get("kwin_script"):
        return Check("kwin_script", label, True, tr("Fensterwechsel kommen ereignisgesteuert an"))
    off = not sv.get("dynamic_mode", True)
    return Check("kwin_script", label, False,
                 tr("Dynamic Mode ist ausgeschaltet") if off else
                 tr("KWin hat das Skript nicht geladen – Dynamic Mode in den Einstellungen "
                    "aus- und wieder einschalten oder den Dienst neu starten"))


def _dbus(sv: dict | None) -> Check:
    label = tr("D-Bus-Dienst io.github.arekown.NeondeckCT angemeldet")
    if sv is None:
        return Check("dbus", label, False, tr(NO_SERVICE))
    ok = bool(sv.get("dbus_service"))
    return Check("dbus", label, ok, tr("KWin kann den Dienst erreichen") if ok else
                 tr("Nicht angemeldet – läuft ein zweiter Dienst? Dann den alten beenden"))


def _session_watcher(sv: dict | None) -> Check:
    label = tr("Sitzungswächter aktiv (Standby, Bildschirmsperre)")
    if sv is None:
        return Check("session_watcher", label, False, tr(NO_SERVICE))
    signals = sv.get("session_watcher") or []
    return Check("session_watcher", label, bool(signals),
                 tr("Abonniert: {signals}", signals=", ".join(signals)) if signals else
                 tr("Keine Signale abonniert – nach Standby/Sperre wird nicht neu gezeichnet"))


def _tool(env: Env, tool: str, label: str) -> Check:
    path = env.which(tool)
    if path:
        return Check(tool.replace("-", "_"), label, True, path)
    return Check(tool.replace("-", "_"), label, False, tr("„{tool}“ nicht gefunden", tool=tool),
                 _install(tool, env.which))


def _service(env: Env, sv: dict | None) -> Check:
    path = (sv or {}).get("socket") or env.socket or socket_path()
    label = tr("Dienst und API-Socket")
    if sv is None:
        return Check("service", label, False, f"{tr(NO_SERVICE)} ({path})", "neondeck-ct &")
    try:
        is_socket = stat.S_ISSOCK(Path(path).stat().st_mode)
    except OSError:
        is_socket = False
    return Check("service", label, True,
                 tr("Dienst antwortet, Socket {path}", path=path)
                 + ("" if is_socket else tr(" (Socket-Datei nicht sichtbar)")))


def _data_dirs(env: Env) -> Check:
    dirs = env.data_dirs if env.data_dirs is not None else [
        paths.config_dir(), paths.data_dir(), paths.state_dir()]
    bad = [d for d in dirs if not _writable_dir(Path(d), env.access)]
    if not bad:
        return Check("data_dirs", tr("Datenordner beschreibbar"), True,
                     ", ".join(str(d) for d in dirs))
    return Check("data_dirs", tr("Datenordner beschreibbar"), False,
                 tr("Nicht beschreibbar: {dirs}", dirs=", ".join(str(d) for d in bad)),
                 "\n".join(f"mkdir -p '{d}' && chmod u+rwx '{d}'" for d in bad))


def _fonts(env: Env) -> Check:
    if env.fonts is not None:
        files = env.fonts
    else:
        from .render.fonts import font_files
        files = font_files()
    missing = [f"{family} ({path})" for family, path in files.items() if not Path(path).is_file()]
    if not missing:
        return Check("fonts", tr("Schriften vorhanden"), True, ", ".join(files))
    return Check("fonts", tr("Schriften vorhanden"), False, tr("Fehlt: {fonts}", fonts="; ".join(missing)),
                 f"{sys.executable} '{REPO / 'tools' / 'fetch_fonts.py'}'")


def _assets(env: Env) -> Check:
    if env.assets_manifest is not None:
        manifest = env.assets_manifest
    else:
        from .core.assets import assets_dir
        manifest = assets_dir() / "manifest.json"
    ok = Path(manifest).is_file()
    return Check("assets", tr("Original-Grafiken importiert"), ok,
                 str(manifest.parent) if ok else tr("Grafiken fehlen – Tasten zeigen nur Text"),
                 None if ok else
                 f"{sys.executable} '{REPO / 'tools' / 'import_assets.py'}' "
                 "--source " + tr("<Pfad zum entpackten Windows-Installer (siehe README)>"))
