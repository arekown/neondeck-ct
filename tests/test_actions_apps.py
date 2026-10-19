"""App fokussieren oder starten (KWin, gtk-launch, Desktop-Dateien); Datenorte der Tests."""
import json

from neondeck.actions import execute
from neondeck.core import desktop_apps
from neondeck.desktop.kwin import KWinWatcher
from support.fake_kwin import FakeBus, FakeKWin
from support.fakes import FakePopen, make_ctx


def test_paths_never_real_home(tmp_path):
    """Waechter: jeder Test arbeitet mit eigenen Datenorten (conftest), nie mit ~/.config."""
    from pathlib import Path

    from neondeck.core import paths
    home = Path.home().resolve()
    for d in (paths.config_dir(), paths.data_dir(), paths.state_dir(), paths.autostart_dir()):
        assert d.resolve().is_relative_to(tmp_path.resolve()), d
        assert not d.resolve().is_relative_to(home / ".config"), d
        assert not d.resolve().is_relative_to(home / ".local"), d


# --- App fokussieren oder starten ---------------------------------------------------------

def test_app_focus_running_vs_start(tmp_path, monkeypatch):
    asked = []

    def focus(app_id, window=""):
        asked.append((app_id, window))
        return app_id == "org.kde.konsole"

    popen = FakePopen()
    r = execute({"type": "app_focus", "app_id": "org.kde.konsole"}, make_ctx(popen=popen,
                                                                             focus=focus))
    assert r.ok and popen.calls == [] and asked == [("org.kde.konsole", "")]
    # laeuft nicht: Start ueber gtk-launch
    r = execute({"type": "app_focus", "app_id": "org.kde.kate"}, make_ctx(popen=popen,
                                                                          focus=focus))
    assert r.ok and popen.calls[-1][0] == ["gtk-launch", "--", "org.kde.kate"]
    assert popen.calls[-1][1]["start_new_session"] is True
    # ohne Fensterwaechter (focus None): auch starten
    r = execute({"type": "app_focus", "app_id": "org.kde.kate"}, make_ctx(popen=popen))
    assert r.ok and popen.calls[-1][0] == ["gtk-launch", "--", "org.kde.kate"]
    # gtk-launch fehlt: kioclient exec <Desktop-Datei>
    apps = tmp_path / "apps"
    (apps / "kde").mkdir(parents=True)
    (apps / "kde" / "kate.desktop").write_text("[Desktop Entry]\nName=Kate\nExec=kate\n")
    monkeypatch.setattr(desktop_apps, "default_dirs", lambda: [tmp_path / "leer", apps])
    popen = FakePopen(missing=("gtk-launch",))
    r = execute({"type": "app_focus", "app_id": "kde-kate"}, make_ctx(popen=popen, focus=focus))
    assert r.ok and popen.calls == [(["kioclient", "exec", str(apps / "kde" / "kate.desktop")],
                                     popen.calls[0][1])]
    r = execute({"type": "app_focus", "app_id": "gibt.es.nicht"}, make_ctx(popen=popen,
                                                                           focus=focus))
    assert not r.ok and "gibt.es.nicht" in r.message
    assert not execute({"type": "app_focus", "app_id": ""}, make_ctx()).ok
    # Fenster-Kachel: bestimmtes Fenster
    asked.clear()
    execute({"type": "app_focus", "app_id": "org.kde.konsole", "window": "{w2}"},
            make_ctx(focus=focus))
    assert asked == [("org.kde.konsole", "{w2}")]


def test_find_desktop_file_stays_in_base(tmp_path):
    base = tmp_path / "apps"
    (base / "kde").mkdir(parents=True)
    (base / "kde" / "kate.desktop").write_text("[Desktop Entry]\n")
    (tmp_path / "boese.desktop").write_text("[Desktop Entry]\n")
    (base / "link.desktop").symlink_to(tmp_path / "boese.desktop")
    assert desktop_apps.find_desktop_file("kde-kate", [base]) == base / "kde" / "kate.desktop"
    for bad in ("..-boese", "kde-..-..-boese", "a--b", "-x", "link", "../boese", ".hidden", ""):
        assert desktop_apps.find_desktop_file(bad, [base]) is None, bad


def test_kwin_focus_specific_window():
    bus, kwin = FakeBus(), FakeKWin()
    w = KWinWatcher(bus=bus, kwin_iface_factory=kwin)
    w.start()
    win = {"resourceClass": "org.kde.konsole", "desktopFileName": "org.kde.konsole",
           "caption": "a", "pid": 1}
    bus.receiver().windowsChanged(json.dumps([dict(win, internalId="{w1}"),
                                              dict(win, internalId="{w2}")]))
    assert w.focus("org.kde.konsole", "{w2}")
    assert 'id = "{w2}"' in kwin.contents[-1]
    assert w.focus("org.kde.konsole", "{weg}")         # Fenster weg: erstes der App
    assert 'id = "{w1}"' in kwin.contents[-1]
    assert w.focus("", "{w2}") and 'id = "{w2}"' in kwin.contents[-1]
    assert not w.focus("", "{weg}")
    w.stop()
