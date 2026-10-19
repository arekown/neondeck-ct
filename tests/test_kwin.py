"""KWin-Fensterwaechter (mit Ersatz-Bus/-KWin) und .desktop-Liste."""
import json
import logging
import os
from pathlib import Path

from PySide6.QtDBus import QDBusConnection

from neondeck.core import desktop_apps, paths
from neondeck.core.windows import WindowInfo
from neondeck.desktop.kwin import (
    FOCUS_SCRIPT_NAME,
    LEGACY_SCRIPT_NAME,
    OBJECT_PATH,
    SCRIPT_NAME,
    SERVICE,
    KWinWatcher,
)
from support.fake_kwin import FakeBus, FakeKWin

SCRIPT = paths.bundled_dir() / "kwin" / "neondeck-ct.js"
FIREFOX = {"resourceClass": "firefox", "desktopFileName": "org.mozilla.firefox",
           "caption": "Start – Mozilla Firefox", "pid": 4711,
           "internalId": "{aaaa-1}"}
KONSOLE = {"resourceClass": "org.kde.konsole", "desktopFileName": "org.kde.konsole",
           "caption": "~ : bash — Konsole", "pid": 3939, "internalId": "{bbbb-2}"}


def make_watcher(**kw):
    bus, kwin = FakeBus(**kw), FakeKWin()
    return KWinWatcher(bus=bus, kwin_iface_factory=kwin), bus, kwin


def test_kwin_watcher_loads_and_unloads_script():
    w, bus, kwin = make_watcher()
    assert w.start()
    assert bus.services == [SERVICE] == ["io.github.arekown.NeondeckCT"]
    obj, options = bus.objects[OBJECT_PATH]
    assert OBJECT_PATH == "/Window"
    assert options == QDBusConnection.RegisterOption.ExportAllSlots
    assert kwin.methods() == [
        ("unloadScript", LEGACY_SCRIPT_NAME),          # Skript unter altem Namen weg
        ("unloadScript", SCRIPT_NAME),                 # liegengebliebenes zuerst weg
        ("loadScript", str(SCRIPT), SCRIPT_NAME),
        ("run",),
    ]
    assert SCRIPT_NAME == "neondeck-ct"
    assert [c[0] for c in kwin.calls] == ["/Scripting"] * 3 + ["/Scripting/Script7"]
    assert kwin.loaded == {SCRIPT_NAME: SCRIPT.read_text(encoding="utf-8")}

    w.stop()
    assert kwin.methods()[-1] == ("unloadScript", SCRIPT_NAME)
    assert kwin.loaded == {}
    assert bus.services == [] and OBJECT_PATH not in bus.objects
    n = len(kwin.calls)
    w.stop()  # zweimal: harmlos
    assert len(kwin.calls) == n


def test_kwin_script_uses_plasma6_api_and_service_names():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in ('"io.github.arekown.NeondeckCT"', '"/Window"', '"io.github.arekown.NeondeckCT.Window"',
                   "workspace.windowActivated.connect", "workspace.windowAdded.connect",
                   "workspace.windowRemoved.connect", "workspace.windowList()",
                   "workspace.activeWindow", '"activated"', '"windowsChanged"',
                   "JSON.stringify", "internalId", "desktopFileName", "resourceClass",
                   # Titel/desktopFileName-Aenderungen je Fenster, in JS gesammelt (QTimer)
                   "w.captionChanged.connect", "w.desktopFileNameChanged.connect",
                   "new QTimer()", "listTimer.singleShot = true"):
        assert needle in text, needle


def test_start_without_service_name_loads_nothing(caplog):
    w, bus, kwin = make_watcher(service_ok=False)
    with caplog.at_level(logging.WARNING):
        assert not w.start()
    assert kwin.calls == [] and bus.objects == {}
    assert "io.github.arekown.NeondeckCT" in caplog.text
    w.stop()
    assert kwin.calls == []


def test_load_failure_reported(caplog):
    bus, kwin = FakeBus(), FakeKWin(script_id=-1)
    w = KWinWatcher(bus=bus, kwin_iface_factory=kwin)
    with caplog.at_level(logging.WARNING):
        assert not w.start()
    assert ("run",) not in kwin.methods()
    assert "KWin-Skript" in caplog.text
    w.stop()
    assert bus.services == []


def test_run_failure_unloads_and_reports(caplog):
    bus, kwin = FakeBus(), FakeKWin(run_ok=False)
    w = KWinWatcher(bus=bus, kwin_iface_factory=kwin)
    with caplog.at_level(logging.WARNING):
        assert not w.start()
    assert kwin.methods()[-2:] == [("run",), ("unloadScript", SCRIPT_NAME)]
    assert kwin.loaded == {} and bus.services == [] and not w.running
    assert "ließ sich nicht starten" in caplog.text


def test_activated_and_windows_changed_signals():
    w, bus, kwin = make_watcher()
    got, lists = [], []
    w.activated.connect(got.append)
    w.windows_changed.connect(lists.append)
    w.start()
    recv = bus.receiver()
    recv.activated("firefox", "org.mozilla.firefox", "Start", 4711)
    assert got == [WindowInfo("firefox", "org.mozilla.firefox", "Start", 4711)]
    assert w.active == got[0]
    recv.windowsChanged(json.dumps([FIREFOX, KONSOLE]))
    assert len(lists) == 1
    assert [i.desktop_file for i in lists[0]] == ["org.mozilla.firefox", "org.kde.konsole"]
    assert lists[0][1] == WindowInfo("org.kde.konsole", "org.kde.konsole", "~ : bash — Konsole",
                                     3939, "{bbbb-2}")
    assert w.windows == lists[0]
    # Kaputtes JSON / falsche Typen: ignoriert, Liste bleibt
    recv.windowsChanged("{kaputt")
    recv.windowsChanged(json.dumps({"a": 1}))
    recv.windowsChanged(json.dumps([{"resourceClass": 3}, "x"]))
    assert len(lists) == 1 and w.windows == lists[0]
    w.stop()


def test_window_info_matches_case_insensitive():
    info = WindowInfo("firefox", "org.mozilla.firefox", "", 1)
    assert info.matches("Org.Mozilla.Firefox") and info.matches("FIREFOX")
    assert not info.matches("konsole") and not info.matches("")
    assert info.app_key == "org.mozilla.firefox"
    assert WindowInfo("Konsole", "", "", 1).app_key == "konsole"
    # wie toLowerCase() im KWin-Skript, nicht casefold (ß bleibt ß)
    assert not WindowInfo("straße", "", "", 1).matches("STRASSE")
    assert WindowInfo("Straße", "", "", 1).matches("STRAßE")


def test_focus_loads_one_shot_script():
    w, bus, kwin = make_watcher()
    w.start()
    bus.receiver().windowsChanged(json.dumps([FIREFOX, KONSOLE]))
    kwin.calls.clear()
    assert w.focus("ORG.KDE.KONSOLE")
    assert kwin.methods()[0] == ("unloadScript", FOCUS_SCRIPT_NAME)
    load = kwin.methods()[1]
    assert load[0] == "loadScript" and load[2] == FOCUS_SCRIPT_NAME
    assert kwin.methods()[2:] == [("run",), ("unloadScript", FOCUS_SCRIPT_NAME)]
    text = kwin.contents[-1]
    assert "workspace.activeWindow = " in text and '"{bbbb-2}"' in text
    assert 'app = "org.kde.konsole"' in text              # lower() wie im Skript
    assert FOCUS_SCRIPT_NAME not in kwin.loaded           # sofort wieder entladen
    assert not Path(load[1]).exists()                     # Einmal-Datei geloescht
    assert SCRIPT_NAME in kwin.loaded                     # Waechter bleibt geladen
    # App ohne Fenster: nichts laden, False (Aufrufer startet die App)
    kwin.calls.clear()
    assert not w.focus("org.gimp.GIMP")
    assert kwin.calls == []
    w.stop()


def test_focus_quotes_ids_safely():
    w, bus, kwin = make_watcher()
    w.start()
    evil_id = 'x"); workspace.foo("%s __APP__'  # auch kein zweites Einsetzen
    evil = dict(KONSOLE, internalId=evil_id, desktopFileName='a"b')
    bus.receiver().windowsChanged(json.dumps([evil]))
    assert w.focus('a"b')
    assert json.dumps(evil_id) in kwin.contents[-1]
    w.stop()


# --- .desktop-Dateien -------------------------------------------------------------------

def _desktop(dir: Path, name: str, body: str) -> None:
    dir.mkdir(parents=True, exist_ok=True)
    (dir / name).write_text(body, encoding="utf-8")


def test_desktop_apps_parse(tmp_path, monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    local = tmp_path / "local"
    flat_user = tmp_path / "flatpak-user"
    flat_sys = tmp_path / "flatpak-sys"
    system = tmp_path / "usr"
    _desktop(system, "org.kde.konsole.desktop",
             "[Desktop Entry]\nType=Application\nName=Konsole\nName[de]=Konsole DE\n"
             "Icon=utilities-terminal\nExec=konsole\nStartupWMClass=konsole\n"
             "[Desktop Action NewWindow]\nName=Neues Fenster\nExec=konsole --new\n")
    _desktop(system, "hidden-helper.desktop",
             "[Desktop Entry]\nType=Application\nName=Helfer\nExec=helper\nNoDisplay=true\n")
    _desktop(system, "link.desktop", "[Desktop Entry]\nType=Link\nName=Web\nURL=https://x\n")
    _desktop(system, "kaputt.desktop", "\x00\x01 kein ini")
    _desktop(system, "brave-browser.desktop",
             "[Desktop Entry]\nType=Application\nName=Brave System\nExec=brave\n")
    # Benutzer-Datei ueberdeckt die Systemdatei gleicher Kennung
    _desktop(local, "brave-browser.desktop",
             "[Desktop Entry]\nType=Application\nName=Brave Web Browser\nExec=brave %U\n"
             "Icon=brave-browser\n")
    # Benutzer blendet eine Systemanwendung aus
    _desktop(system, "org.kde.dolphin.desktop",
             "[Desktop Entry]\nType=Application\nName=Dolphin\nExec=dolphin\n")
    _desktop(local, "org.kde.dolphin.desktop",
             "[Desktop Entry]\nType=Application\nName=Dolphin\nHidden=true\n")
    _desktop(flat_sys, "org.mozilla.firefox.desktop",
             "[Desktop Entry]\nType=Application\nName=Firefox\nIcon=org.mozilla.firefox\n"
             "Exec=/usr/bin/flatpak run --branch=stable --command=firefox org.mozilla.firefox"
             " %u\nStartupWMClass=firefox\n")
    _desktop(flat_user / "sub", "tool.desktop",
             "[Desktop Entry]\nType=Application\nName=Werkzeug\nExec=tool\nNoDisplay=false\n")

    apps = desktop_apps.list_apps([local, flat_user, flat_sys, system])
    by_id = {a.id: a for a in apps}
    assert set(by_id) == {"org.kde.konsole", "brave-browser", "org.mozilla.firefox", "sub-tool"}
    assert by_id["org.kde.konsole"] == desktop_apps.DesktopApp(
        "org.kde.konsole", "Konsole DE", "utilities-terminal", "konsole", "konsole")
    assert by_id["brave-browser"].name == "Brave Web Browser"
    ff = by_id["org.mozilla.firefox"]
    assert (ff.wm_class, ff.icon) == ("firefox", "org.mozilla.firefox")
    assert ff.exec.startswith("/usr/bin/flatpak run")
    assert by_id["sub-tool"].wm_class == ""
    assert [a.name for a in apps] == sorted((a.name for a in apps), key=str.casefold)


def test_desktop_apps_default_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_DIRS", raising=False)
    dirs = [str(d) for d in desktop_apps.default_dirs()]
    assert dirs == [str(tmp_path / ".local/share/applications"),
                    str(tmp_path / ".local/share/flatpak/exports/share/applications"),
                    "/usr/local/share/applications",
                    "/usr/share/applications",
                    "/var/lib/flatpak/exports/share/applications",
                    "/var/lib/snapd/desktop/applications"]
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_DIRS", "/opt/x/share:/var/lib/flatpak/exports/share:/usr/share")
    dirs = [str(d) for d in desktop_apps.default_dirs()]
    assert dirs == [str(tmp_path / "data/applications"),
                    str(tmp_path / "data/flatpak/exports/share/applications"),
                    "/opt/x/share/applications",
                    "/var/lib/flatpak/exports/share/applications",
                    "/usr/share/applications",
                    "/var/lib/snapd/desktop/applications",
                    "/usr/local/share/applications"]
    assert all(os.path.isabs(d) for d in dirs)


def test_desktop_apps_escapes_show_in_and_try_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("LANG", "C")
    d = tmp_path / "apps"
    tool = tmp_path / "bin" / "tool"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    _desktop(d, "esc.desktop", "[Desktop Entry]\nType=Application\nName=Mit\\sLeer\\tTab\n"
             "Exec=prog --a=\\\\x\\n\n")
    _desktop(d, "only-gnome.desktop",
             "[Desktop Entry]\nType=Application\nName=Gnome\nOnlyShowIn=GNOME;Unity;\n")
    _desktop(d, "only-kde.desktop",
             "[Desktop Entry]\nType=Application\nName=KdeNur\nOnlyShowIn=KDE;\n")
    _desktop(d, "not-kde.desktop",
             "[Desktop Entry]\nType=Application\nName=NichtKde\nNotShowIn=KDE;\n")
    _desktop(d, "try-missing.desktop",
             "[Desktop Entry]\nType=Application\nName=Fehlt\nTryExec=gibtsnicht-xyz-123\n")
    _desktop(d, "try-abs-missing.desktop",
             "[Desktop Entry]\nType=Application\nName=FehltAbs\nTryExec=/nirgends/tool\n")
    _desktop(d, "try-abs.desktop",
             f"[Desktop Entry]\nType=Application\nName=Da\nTryExec={tool}\n")
    _desktop(d, "try-path.desktop",
             "[Desktop Entry]\nType=Application\nName=Shell\nTryExec=sh\n")
    by_id = {a.id: a for a in desktop_apps.list_apps([d])}
    assert set(by_id) == {"esc", "only-kde", "try-abs", "try-path"}
    assert by_id["esc"].name == "Mit Leer\tTab"
    assert by_id["esc"].exec == "prog --a=\\x\n"
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    ids = {a.id for a in desktop_apps.list_apps([d])}
    assert "only-gnome" in ids and "not-kde" in ids and "only-kde" not in ids
    monkeypatch.delenv("XDG_CURRENT_DESKTOP")  # Dienst ohne Umgebung: KDE angenommen
    assert "only-kde" in {a.id for a in desktop_apps.list_apps([d])}
