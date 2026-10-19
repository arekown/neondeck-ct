"""Dynamic Mode (Profil folgt dem aktiven Fenster) und Seite je Profil."""
import json
import os

import pytest

from neondeck.core.settings import Settings
from neondeck.core.windows import WindowInfo
from neondeck.desktop.kwin import KWinWatcher
from neondeck.engine.dynamic_mode import DEBOUNCE_S, DynamicMode
from neondeck.profile.model import Profile, TouchPage, Workspace
from neondeck.profile.store import ProfileStore
from neondeck.service import app as app_main
from support.engine_rig import make_engine
from support.fake_kwin import FakeBus, FakeKWin
from support.fakes import Clock, FakeDevice, FakeKeyboard, Timers
from support.waiting import wait_until

FIREFOX = WindowInfo("firefox", "org.mozilla.firefox", "Start – Mozilla Firefox", 4711)
FIREFOX2 = WindowInfo("firefox", "org.mozilla.firefox", "Zweites Fenster", 4711)
KONSOLE = WindowInfo("org.kde.konsole", "", "~ : bash — Konsole", 3939)
GIMP = WindowInfo("gimp", "org.gimp.GIMP", "GIMP", 99)
OBS = WindowInfo("obs", "com.obsproject.Studio", "OBS 31", 77)


def save(store, pid, *, app_ids=(), dynamic=True, hold=False):
    p = Profile.empty(pid, pid.upper())
    p.app_ids, p.dynamic, p.hold_profile = list(app_ids), dynamic, hold
    store.save(p)


class Rig:
    def __init__(self, tmp_path, current="default"):
        self.store = ProfileStore(tmp_path / "profiles")
        save(self.store, "default")
        save(self.store, "fx", app_ids=["org.mozilla.firefox"])
        save(self.store, "term", app_ids=["ORG.KDE.KONSOLE"])  # Gross/klein egal
        save(self.store, "obs", app_ids=["com.obsproject.Studio"], hold=True)
        self.current = current
        self.switches = []
        self.clock = Clock(1000.0)
        self.timers = Timers(self.clock)
        self.dm = DynamicMode(self.store, self.activate, self.clock, call_later=self.timers,
                              current=lambda: self.current)  # Standard-Ignorierliste

    def activate(self, pid):
        self.switches.append(pid)
        self.current = pid

    def window(self, info, settle=True):
        self.dm.on_window(info)
        if settle:
            self.timers.advance(DEBOUNCE_S + 0.01)


def test_matches_desktop_file_and_class(tmp_path):
    rig = Rig(tmp_path)
    rig.window(FIREFOX)               # desktopFileName
    assert rig.switches == ["fx"]
    rig.window(KONSOLE)               # resourceClass (kein desktopFileName), Gross/klein
    assert rig.switches == ["fx", "term"]
    rig.window(KONSOLE)               # schon aktiv: kein erneuter Wechsel
    assert rig.switches == ["fx", "term"]


def test_fallback_default(tmp_path):
    rig = Rig(tmp_path, current="fx")
    rig.window(GIMP)
    assert rig.switches == ["default"]
    rig.window(GIMP)
    assert rig.switches == ["default"]


def test_hold_profile_stays(tmp_path):
    rig = Rig(tmp_path)
    rig.window(OBS)
    assert rig.switches == ["obs"]
    rig.window(GIMP)                  # kein eigenes Profil -> OBS haelt
    assert rig.current == "obs" and rig.switches == ["obs"]
    rig.window(FIREFOX)               # eigenes Profil -> wechselt trotzdem
    assert rig.switches == ["obs", "fx"]


def test_pause_after_manual_until_other_app(tmp_path):
    rig = Rig(tmp_path)
    rig.window(FIREFOX)
    assert rig.switches == ["fx"]
    rig.current = "obs"               # Nutzer waehlt OBS von Hand (am Geraet/Editor)
    rig.dm.on_manual_switch("obs")
    rig.window(FIREFOX2)              # gleiche App, anderes Fenster: Pause haelt
    rig.window(FIREFOX)
    assert rig.current == "obs" and rig.switches == ["fx"]
    rig.window(KONSOLE)               # andere App: Automatik wieder an
    assert rig.switches == ["fx", "term"]
    rig.window(FIREFOX)
    assert rig.switches == ["fx", "term", "fx"]


def test_manual_switch_before_any_window_pauses_until_first_window(tmp_path):
    rig = Rig(tmp_path)
    rig.current = "obs"
    rig.dm.on_manual_switch("obs")
    rig.window(FIREFOX)               # noch keine App bekannt -> jeder Fokus ist „andere App“
    assert rig.switches == ["fx"]


def test_debounce_20_events_one_switch(tmp_path):
    rig = Rig(tmp_path)
    apps = [FIREFOX, KONSOLE, GIMP, OBS]
    for i in range(20):               # 20 Aktivierungen in 1 s (alle 50 ms)
        rig.window(apps[i % 4], settle=False)
        rig.timers.advance(0.05)
    assert rig.switches == []         # waehrend des Sturms: kein Flackern
    rig.timers.advance(DEBOUNCE_S)
    assert rig.switches == ["obs"]    # genau ein Wechsel, auf das zuletzt aktive Fenster
    assert pytest.approx(0.15) == DEBOUNCE_S


def test_debounce_one_switch_per_150ms(tmp_path):
    rig = Rig(tmp_path)
    times = []
    rig.dm._activate = lambda pid: (times.append(rig.clock.t), rig.activate(pid))
    for i in range(40):
        rig.window([FIREFOX, KONSOLE][i % 2], settle=False)
        rig.timers.advance(0.2)       # langsamer als die Entprellung: jeder zaehlt
    assert len(times) == 40
    assert all(b - a >= DEBOUNCE_S - 1e-9 for a, b in zip(times, times[1:]))


def test_profile_dynamic_false_never_auto(tmp_path):
    rig = Rig(tmp_path)
    save(rig.store, "fx", app_ids=["org.mozilla.firefox"], dynamic=False)
    rig.window(FIREFOX)
    assert rig.switches == []         # nie automatisch aktiviert (Standard ist schon aktiv)
    rig.current = "term"
    rig.window(FIREFOX)
    assert rig.switches == ["default"]


def test_global_off_does_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.dm.enabled = False
    rig.window(FIREFOX)
    assert rig.switches == [] and rig.timers.pending == []
    rig.dm.enabled = True
    rig.window(FIREFOX)
    assert rig.switches == ["fx"]


IGNORED = {
    "editor": WindowInfo("neondeck-ct", "neondeck-ct", "Neondeck CT", 1),
    "editor_class_only": WindowInfo("Neondeck-CT", "", "Neondeck CT", 1),
    "plasmashell": WindowInfo("plasmashell", "org.kde.plasmashell", "Arbeitsfläche", 2),
    "plasmashell_no_desktop_file": WindowInfo("plasmashell", "", "", 2),
    "krunner": WindowInfo("krunner", "org.kde.krunner", "KRunner", 3),
    "krunner_desktop_file_only": WindowInfo("x", "ORG.KDE.KRUNNER", "KRunner", 3),
    "kwin_internal_empty_class": WindowInfo("", "", "", 0),
    "empty_class_with_desktop_file": WindowInfo("", "org.kde.konsole", "?", 5),
}


@pytest.mark.parametrize("name", sorted(IGNORED))
def test_desktop_shell_editor_and_internal_windows_ignored(tmp_path, name):
    rig = Rig(tmp_path, current="fx")
    rig.window(IGNORED[name])
    assert rig.switches == [] and rig.timers.pending == []   # nicht einmal entprellt


@pytest.mark.parametrize("name", sorted(IGNORED))
def test_ignored_windows_do_not_end_manual_pause(tmp_path, name):
    rig = Rig(tmp_path)
    rig.window(FIREFOX)
    rig.current = "obs"
    rig.dm.on_manual_switch("obs")
    rig.window(IGNORED[name])         # z. B. Klick auf die Arbeitsfläche
    rig.window(FIREFOX)               # dieselbe App wie vor der Pause: Pause haelt
    assert rig.current == "obs" and rig.switches == ["fx"]


def test_ignored_window_between_storm_does_not_flicker(tmp_path):
    rig = Rig(tmp_path)
    rig.window(FIREFOX, settle=False)
    rig.timers.advance(0.05)
    rig.window(IGNORED["plasmashell"], settle=False)
    rig.timers.advance(DEBOUNCE_S)
    assert rig.switches == ["fx"]


def test_profile_changes_picked_up_and_broken_files_skipped(tmp_path):
    rig = Rig(tmp_path)
    rig.window(GIMP)
    assert rig.switches == []
    save(rig.store, "gimp", app_ids=["org.gimp.GIMP"])
    (rig.store.dir / "kaputt.json").write_text("{kaputt")
    # mtime-Aufloesung: Datei sicher als geaendert erkennen
    st = os.stat(rig.store.path("gimp"))
    os.utime(rig.store.path("gimp"), ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    rig.window(GIMP)
    assert rig.switches == ["gimp"]


def test_unknown_activate_failure_logged_not_raised(tmp_path, caplog):
    rig = Rig(tmp_path)

    def boom(pid):
        raise RuntimeError("kaputt")

    rig.dm._activate = boom
    rig.window(FIREFOX)               # Ausnahme bleibt im Dynamic Mode
    assert "kaputt" in caplog.text


# --- Seite je Profil ---------------------------------------------------------------------

def two_ws(pid):
    p = Profile.empty(pid, pid)
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    p.workspaces.append(Workspace("ws2", "Zwei", [TouchPage("a", "A"), TouchPage("b", "B"),
                                                  TouchPage("c", "C")]))
    return p


def test_last_page_restored(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    a, b = two_ws("a"), two_ws("b")
    e = make_engine(a)
    e.call("workspace", {"id": "ws2"})
    e.call("page", {"index": 2})
    e.set_profile(b)
    assert (e.workspace_id, e.page_index) == ("ws1", 0)   # b: Heim-Arbeitsbereich
    e.call("page", {"index": 1})
    e.set_profile(a)
    assert (e.workspace_id, e.page_index) == ("ws2", 2)   # a: gemerkt
    views = e.remembered_views()
    assert views == {"a": {"workspace": "ws2", "page": 2}, "b": {"workspace": "ws1", "page": 1}}

    # ueber Neustart: Einstellungen speichern und laden
    s = Settings(last_pages=views)
    s.save()
    loaded = Settings.load()
    assert loaded.last_pages == views
    e2 = make_engine(two_ws("a"), views=loaded.last_pages)
    assert (e2.workspace_id, e2.page_index) == ("ws2", 2)
    e2.set_profile(two_ws("b"))
    assert (e2.workspace_id, e2.page_index) == ("ws1", 1)


def test_last_page_bool_page_rejected_and_deleted_profiles_pruned():
    e = make_engine(two_ws("a"), views={"a": {"workspace": "ws2", "page": True},
                                        "weg": {"workspace": "ws1", "page": 0}})
    assert (e.workspace_id, e.page_index) == ("ws1", 0)     # True ist keine Seite
    assert "weg" in e.remembered_views()
    assert e.remembered_views(existing=["a"]) == {"a": {"workspace": "ws1", "page": 0}}
    assert "weg" not in e.remembered_views()                # dauerhaft vergessen


def test_last_page_rolled_back_when_new_profile_fails():
    e = make_engine(two_ws("a"))
    e.call("workspace", {"id": "ws2"})
    before = dict(e.view.views)
    e.painter.refresh = lambda now=None: (_ for _ in ()).throw(RuntimeError("kaputt"))
    with pytest.raises(RuntimeError):
        e.set_profile(two_ws("b"))
    assert e.profile.id == "a" and e.view.views == before == {}
    assert e.remembered_views() == {"a": {"workspace": "ws2", "page": 0}}


def test_last_page_invalid_entries_fall_back():
    p = two_ws("a")
    e = make_engine(p, views={"a": {"workspace": "weg", "page": 1}})
    assert (e.workspace_id, e.page_index) == ("ws1", 0)
    e = make_engine(two_ws("a"), views={"a": {"workspace": "ws2", "page": 9}})
    assert (e.workspace_id, e.page_index) == ("ws2", 0)
    e = make_engine(two_ws("a"), views={"a": "kaputt"})
    assert (e.workspace_id, e.page_index) == ("ws1", 0)


def test_settings_last_pages_and_dynamic_mode_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    path = tmp_path / "config" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dynamic_mode": False, "last_pages": {
        "a": {"workspace": "ws2", "page": 1}, "b": {"workspace": 3, "page": 1},
        "c": {"workspace": "x", "page": -1}, "d": [1]}}))
    s = Settings.load()
    assert s.dynamic_mode is False
    assert s.last_pages == {"a": {"workspace": "ws2", "page": 1}}
    path.write_text(json.dumps({"dynamic_mode": "ja", "last_pages": []}))
    s = Settings.load()
    assert s.dynamic_mode is True and s.last_pages == {}


# --- Dienst ----------------------------------------------------------------------------

@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    bus, kwin = FakeBus(), FakeKWin()
    monkeypatch.setattr(app_main, "_make_window_watcher",
                        lambda: KWinWatcher(bus=bus, kwin_iface_factory=kwin))
    store = ProfileStore(tmp_path / "config" / "profiles")
    save(store, "default")
    save(store, "fx", app_ids=["org.mozilla.firefox"])
    app = app_main.App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    yield app, bus, kwin
    app.quit()


def settled(app) -> bool:
    """Kein Fensterwechsel mehr in der Entprellung: das letzte Fenster ist ausgewertet."""
    return not app.dynamic._scheduled and app.dynamic._pending is None


def test_service_follows_window_and_reports(service):
    app, bus, kwin = service
    events = []
    app.add_listener(lambda name, data: events.append((name, data)))
    assert kwin.methods()[2][:1] == ("loadScript",) and app.dynamic_mode is True
    bus.receiver().activated("firefox", "org.mozilla.firefox", "Start", 4711)
    assert ("window.active", {"resource_class": "firefox", "desktop_file": "org.mozilla.firefox",
                              "caption": "Start", "pid": 4711}) in events
    assert wait_until(lambda: app.engine.profile.id == "fx")
    assert Settings.load().active_profile == "fx"
    # manueller Wechsel pausiert bis zur naechsten anderen App
    app.switch_profile("default")
    bus.receiver().activated("firefox", "org.mozilla.firefox", "Zwei", 4711)
    assert wait_until(lambda: settled(app))  # Entprellung abwarten
    assert app.engine.profile.id == "default"
    # global aus
    app.settings_controller.apply({"dynamic_mode": False})
    assert app.dynamic_mode is False and Settings.load().dynamic_mode is False
    bus.receiver().activated("gimp", "org.gimp.GIMP", "GIMP", 9)
    bus.receiver().activated("firefox", "org.mozilla.firefox", "Start", 4711)
    assert wait_until(lambda: settled(app))
    assert app.engine.profile.id == "default"


def test_service_ignores_desktop_and_editor(service):
    app, bus, kwin = service
    bus.receiver().activated("firefox", "org.mozilla.firefox", "Start", 4711)
    assert wait_until(lambda: app.engine.profile.id == "fx")
    for args in (("plasmashell", "org.kde.plasmashell", "", 1), ("krunner", "", "", 2),
                 ("", "", "", 0), ("neondeck-ct", "neondeck-ct", "Editor", 3)):
        bus.receiver().activated(*args)
    assert wait_until(lambda: settled(app))
    assert app.engine.profile.id == "fx"


def test_service_retries_watcher_when_dynamic_mode_switched_on(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    bus, kwin = FakeBus(service_ok=False), FakeKWin()
    watcher = KWinWatcher(bus=bus, kwin_iface_factory=kwin)
    monkeypatch.setattr(app_main, "_make_window_watcher", lambda: watcher)
    app = app_main.App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert not watcher.running and app.dynamic_mode is False
        bus.service_ok = True         # z. B. KWin/Session-Bus war beim Start noch nicht da
        app.settings_controller.apply({"dynamic_mode": True})
        assert watcher.running and app.dynamic_mode is True
        assert kwin.methods()[-1] == ("run",)
        n = len(kwin.calls)
        app.settings_controller.apply({"dynamic_mode": True})  # laeuft schon: kein zweites Laden
        assert len(kwin.calls) == n
    finally:
        app.quit()


def test_service_saves_only_existing_profiles_pages(service, tmp_path):
    app, bus, kwin = service
    app.engine.view.views["geloescht"] = ("ws1", 0)
    app.quit()
    assert "geloescht" not in Settings.load().last_pages


def test_service_quit_unloads_script_and_saves_pages(service):
    app, bus, kwin = service
    app.engine.call("page", {"index": 0})
    app.quit()
    assert kwin.methods()[-1] == ("unloadScript", "neondeck-ct")
    assert bus.services == []
    assert Settings.load().last_pages == {"default": {"workspace": app.engine.workspace_id,
                                                      "page": 0}}
