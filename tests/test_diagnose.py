"""Diagnose: Pruefungen (Geraet, uinput, udev), udev-Regel, Firmware-Version.

Alles offscreen, mit eigenen Socket-Namen und Ersatz-Geraet; kein Test liest echte
Datenorte (conftest) oder fuehrt einen Reparaturbefehl aus.
"""
import subprocess
from pathlib import Path

import pytest

from neondeck import (
    actions,  # noqa: F401 - registriert alle Aktionen
    diagnose,
)
from neondeck.api.router import Later
from neondeck.device.ct import CTDevice
from neondeck.diagnose import UDEV_RULES, UDEV_RULES_PATH, Env, run_checks, udev_fix
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def _fake_tty(root: Path, name: str, product: str) -> None:
    d = root / name
    (d / "device").mkdir(parents=True)
    (d / "idVendor").write_text("2ec2\n")
    (d / "idProduct").write_text(product + "\n")


def _env(tmp_path, **kw) -> Env:
    manifest = tmp_path / "assets" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}")
    font = tmp_path / "font.ttf"
    font.write_bytes(b"x")
    defaults = dict(environ={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"},
                    tty_root=str(tmp_path / "tty"), uinput=str(tmp_path / "uinput"),
                    which=lambda tool: f"/usr/bin/{tool}", access=lambda path, mode: True,
                    data_dirs=[tmp_path / "data"], fonts={"Inter": font},
                    assets_manifest=manifest, socket=str(tmp_path / "sock"))
    defaults.update(kw)
    return Env(**defaults)


def _by_id(checks) -> dict:
    return {c.id: c for c in checks}


# --- Diagnose ---------------------------------------------------------------------------

def test_checks_report_missing_uinput(tmp_path, monkeypatch):
    def no_process(*a, **k):
        raise AssertionError("Diagnose darf nichts ausführen")
    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)

    _fake_tty(tmp_path / "tty", "ttyACM3", "0007")  # zweite CT-Revision
    checks = _by_id(run_checks(service=None, env=_env(tmp_path)))
    uinput = checks["uinput"]
    assert not uinput.ok and "fehlt" in uinput.detail
    assert "sudo modprobe uinput" in uinput.fix and UDEV_RULES in uinput.fix
    assert checks["device"].ok and "/dev/ttyACM3 (2ec2:0007)" in checks["device"].detail
    assert checks["session"].ok and checks["wl_copy"].ok and checks["fonts"].ok
    for cid in ("firmware", "kwin_script", "dbus", "session_watcher", "service"):
        assert not checks[cid].ok and diagnose.NO_SERVICE in checks[cid].detail

    # vorhanden, aber nicht beschreibbar; Werkzeuge fehlen (dnf-Befehl), Datenordner gesperrt
    (tmp_path / "uinput").write_text("")
    env = _env(tmp_path, access=lambda path, mode: False,
               which=lambda tool: "/usr/bin/dnf" if tool == "dnf" else None)
    checks = _by_id(run_checks(service={"connected": True, "serial": "S1", "firmware": "0.2.8",
                                        "kwin_script": True, "dbus_service": True,
                                        "session_watcher": ["PrepareForSleep"],
                                        "socket": str(tmp_path / "sock")}, env=env))
    assert not checks["uinput"].ok and "Schreibrecht" in checks["uinput"].detail
    assert checks["uinput"].fix == udev_fix()
    assert not checks["tty_access"].ok and checks["tty_access"].fix == udev_fix()
    assert checks["wl_copy"].fix == "sudo dnf install wl-clipboard"
    assert checks["pactl"].fix == "sudo dnf install pulseaudio-utils"
    assert not checks["setpriv"].ok
    assert not checks["data_dirs"].ok and "mkdir -p" in checks["data_dirs"].fix
    assert checks["firmware"].ok and "0.2.8" in checks["firmware"].detail
    assert checks["kwin_script"].ok and checks["dbus"].ok and checks["session_watcher"].ok
    assert checks["service"].ok
    assert all("sudo" not in (c.fix or "") or c.id in (
        "uinput", "tty_access", "wl_copy", "pactl", "setpriv") for c in checks.values())


def test_udev_rule_text_exact():
    assert UDEV_RULES_PATH == "/etc/udev/rules.d/70-neondeck-ct.rules"
    assert UDEV_RULES.splitlines() == [
        'SUBSYSTEM=="tty", ACTION=="add", ATTRS{idVendor}=="2ec2", '
        'ATTRS{idProduct}=="0003|0007", MODE="0660", TAG+="uaccess"',
        'KERNEL=="uinput", SUBSYSTEM=="misc", ACTION=="add", TAG+="uaccess", '
        'OPTIONS+="static_node=uinput"']
    fix = udev_fix()
    assert f"sudo tee {UDEV_RULES_PATH}" in fix and UDEV_RULES in fix
    assert fix.endswith("sudo udevadm control --reload-rules && sudo udevadm trigger")


def test_firmware_version_from_device_and_diag(editor_service):
    dev = CTDevice(port_finder=lambda: None)
    assert dev.firmware_version(request=True) is None  # nicht verbunden: nichts gesendet
    dev._dispatch([bytes([0x06, 0x07, 0x05, 0, 2, 8])])  # Antwort auf 0x07
    assert dev.firmware_version() == "0.2.8"

    app, server = editor_service.app, editor_service.server
    reply = server.methods["diag"](None, {})  # Geraet getrennt: sofort
    assert {c["id"] for c in reply["checks"]} >= {"uinput", "firmware", "device", "fonts"}
    assert reply["service"]["socket"] and not reply["service"]["connected"]

    asked = []

    def firmware_version(request=False):
        asked.append(request)
        return "1.4.0" if len(asked) > 1 else None

    app.device.firmware_version = firmware_version
    app.device_link.on_state(True)
    later = server.methods["diag"](None, {})  # Firmware kommt erst mit der Antwort des Geraets
    assert isinstance(later, Later)
    got = []
    later.on_done = lambda result, error: got.append((result, error))
    assert wait_until(lambda: got)
    result, error = got[0]
    assert error is None and result["service"]["firmware"] == "1.4.0"
    assert _by_id(diagnose.run_checks(service=result["service"]))["firmware"].ok
    app.device_link.on_state(False)
