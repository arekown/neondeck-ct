"""Fenster platzieren: Wunschliste (Qt-frei), D-Bus-Antwort des Waechters, KWin-Skript
(in QJSEngine mit Ersatz-``workspace``) und die Aktionen ``run``/``app_focus``."""
import json

from PySide6.QtQml import QJSEngine

from neondeck.actions import execute
from neondeck.core import paths
from neondeck.core.placement import (
    EXPECT_S,
    PlacementBook,
    app_key_of,
    normalize_screen,
    window_matches,
)
from neondeck.desktop.kwin import KWinWatcher
from support.fake_kwin import FakeBus, FakeKWin
from support.fakes import Clock, FakePopen, make_ctx

SCRIPT = paths.bundled_dir() / "kwin" / "neondeck-ct.js"


# --- Wunschliste ----------------------------------------------------------------------------

def test_matching_rules():
    assert window_matches("konsole", "org.kde.konsole", "org.kde.konsole")  # Wayland-Klasse
    assert window_matches("org.kde.konsole", "konsole", "")                 # X11-Klasse
    assert window_matches("STEAM", "steam", "")
    assert window_matches("com.spotify.Client.desktop", "spotify", "com.spotify.Client")
    assert not window_matches("kate", "org.kde.konsole", "org.kde.konsole")
    assert not window_matches("", "x", "x")
    assert app_key_of(["/usr/bin/steam", "-silent"]) == "steam"
    assert app_key_of(["flatpak", "run", "--branch=stable", "com.spotify.Client"]) \
        == "com.spotify.Client"
    assert normalize_screen(" Rechts ") == "right" and normalize_screen("oben") == "top"
    assert normalize_screen("DP-3") == "DP-3" and normalize_screen("CENTER") == "center"


def test_book_claims_in_order_prefers_pid_and_expires():
    clock = Clock(100.0)
    book = PlacementBook(clock)
    assert book.expect("konsole") is None                  # nichts zu tun
    assert book.expect("", "DP-1", "left") is None          # keine App
    a = book.expect("konsole", "links", "top_left")
    b = book.expect("konsole", "", "maximize", pid=42)
    # gleicher Prozess vor gleicher App
    assert book.claim("org.kde.konsole", "org.kde.konsole", 42) is b and b.done.is_set()
    assert book.claim("kate", "org.kde.kate", 7) is None
    hit = book.claim("org.kde.konsole", "org.kde.konsole", 7)
    assert hit is a and hit.reply() == {"screen": "left", "place": "top_left"}
    assert a.wait(0) and book.pending() == []
    # abgelaufen
    book.expect("steam", "DP-3", "maximize")
    clock.t += EXPECT_S + 1
    assert book.claim("steam", "steam", 1) is None and book.pending() == []
    # unbekannter Platz zaehlt als "none"
    assert book.expect("kate", "", "irgendwo") is None


def test_watcher_answers_placement_over_dbus():
    bus, kwin = FakeBus(), FakeKWin()
    w = KWinWatcher(bus=bus, kwin_iface_factory=kwin)
    assert w.expect_window("konsole", "DP-3", "left") is None  # Skript laeuft nicht
    w.start()
    recv = bus.receiver()
    assert recv.metaObject().indexOfSlot("placement(QString,QString,int)") >= 0
    ticket = w.expect_window("konsole", "rechts", "top_right")
    assert recv.placement("firefox", "org.mozilla.firefox", 5) == ""
    assert json.loads(recv.placement("org.kde.konsole", "org.kde.konsole", 6)) == {
        "screen": "right", "place": "top_right"}
    assert ticket.wait(0)
    assert recv.placement("org.kde.konsole", "org.kde.konsole", 7) == ""  # nur einmal
    w.stop()


# --- KWin-Skript ----------------------------------------------------------------------------

STUBS = """
var dbus = [], added = [];
function QTimer() { this.timeout = {connect: function () {}}; this.active = false;
                    this.start = function () {}; }
var KWin = {MaximizeArea: 2};
function out(name, x, y, w, h, area) {
    return {name: name, geometry: {x: x, y: y, width: w, height: h}, area: area};
}
var workspace = {
    screens: [out("HDMI-A-1", 2560, 0, 2560, 1440, {x: 2560, y: 40, width: 2560, height: 1400}),
              out("DP-1", 0, 1440, 2560, 1440, {x: 0, y: 1440, width: 2560, height: 1440}),
              out("DP-2", 2560, 1440, 2560, 1440, {x: 2560, y: 1440, width: 2560, height: 1396}),
              out("DP-3", 5120, 1440, 2560, 1440, {x: 5120, y: 1440, width: 2560, height: 1440})],
    currentDesktop: {}, activeWindow: null,
    windowList: function () { return []; },
    clientArea: function (option, output, desktop) { return output.area; },
    windowActivated: {connect: function () {}},
    windowAdded: {connect: function (f) { added.push(f); }},
    windowRemoved: {connect: function () {}}
};
function callDBus() { dbus.push(Array.prototype.slice.call(arguments)); }
function newWindow(rc) {
    var w = {normalWindow: true, skipTaskbar: false, resourceClass: rc, desktopFileName: rc,
             caption: "", pid: 99, internalId: "{1}", maximizable: true, max: null,
             output: workspace.screens[2],
             frameGeometry: {x: 2600, y: 1500, width: 900, height: 600},
             captionChanged: {connect: function () {}},
             desktopFileNameChanged: {connect: function () {}},
             setMaximize: function (v, h) { this.max = [v, h]; }};
    added[0](w);
    return w;
}
function place(reply) {
    var w = newWindow("org.kde.konsole");
    var call = dbus[dbus.length - 1];
    call[call.length - 1](reply);  // Rueckruf mit der Antwort des Dienstes
    return JSON.stringify({g: w.frameGeometry, max: w.max});
}
"""


def _engine():
    engine = QJSEngine()
    res = engine.evaluate(STUBS + SCRIPT.read_text(encoding="utf-8"))
    assert not res.isError(), res.toString()
    return engine


def _place(engine, screen, place):
    reply = json.dumps({"screen": screen, "place": place}) if place else ""
    res = engine.evaluate(f"place({json.dumps(reply)})")
    assert not res.isError(), res.toString()
    return json.loads(res.toString())


def test_script_asks_service_for_each_new_window():
    engine = _engine()
    res = engine.evaluate("newWindow('org.kde.kate'); JSON.stringify(dbus[dbus.length - 1]"
                          ".slice(0, 7))")
    assert json.loads(res.toString()) == [
        "io.github.arekown.NeondeckCT", "/Window", "io.github.arekown.NeondeckCT.Window", "placement",
        "org.kde.kate", "org.kde.kate", 99]


def test_script_places_on_screens_by_name_and_position():
    engine = _engine()
    g = lambda screen, place: _place(engine, screen, place)["g"]  # noqa: E731 - kurze Hilfe im Test
    assert g("DP-3", "top_right") == {"x": 6400, "y": 1440, "width": 1280, "height": 720}
    assert g("dp-1", "left") == {"x": 0, "y": 1440, "width": 1280, "height": 1440}
    assert g("right", "bottom_left") == {"x": 5120, "y": 2160, "width": 1280, "height": 720}
    # mitte: DP-2 und HDMI-A-1 gleich mittig -> der untere; oben: HDMI-A-1 (ohne Leiste)
    assert g("center", "top") == {"x": 2560, "y": 1440, "width": 2560, "height": 698}
    assert g("top", "bottom_right") == {"x": 3840, "y": 740, "width": 1280, "height": 700}
    assert g("bottom", "right") == {"x": 3840, "y": 1440, "width": 1280, "height": 1396}
    # ohne Bildschirm: der des Fensters (DP-2); "none" = Groesse behalten, mittig
    assert g("", "left") == {"x": 2560, "y": 1440, "width": 1280, "height": 1396}
    assert g("DP-3", "none") == {"x": 5950, "y": 1860, "width": 900, "height": 600}
    # unbekannter Bildschirm: bleibt auf seinem
    assert g("HDMI-9", "right")["x"] == 3840


def test_script_maximizes_and_ignores_empty_or_broken_replies():
    engine = _engine()
    got = _place(engine, "left", "maximize")
    assert got["g"] == {"x": 0, "y": 1440, "width": 2560, "height": 1440}
    assert got["max"] == [True, True]
    got = _place(engine, "DP-3", "left")
    assert got["max"] == [False, False]  # maximiert gemeldetes Fenster erst zuruecksetzen
    unchanged = {"x": 2600, "y": 1500, "width": 900, "height": 600}
    assert _place(engine, "", "") == {"g": unchanged, "max": None}
    res = engine.evaluate("place('{kaputt')")
    assert json.loads(res.toString()) == {"g": unchanged, "max": None}


# --- Aktionen run / app_focus ----------------------------------------------------------------

class Placer:
    def __init__(self):
        self.book = PlacementBook()
        self.asked = []

    def __call__(self, app, screen, place):
        self.asked.append((app, screen, place))
        return self.book.expect(app, screen, place)


def test_run_places_window_of_started_program():
    placer, popen = Placer(), FakePopen(pids=[321])
    r = execute({"type": "run", "command": "steam -silent", "screen": "DP-3",
                 "place": "maximize"}, make_ctx(popen=popen, place=placer))
    assert r.ok and popen.calls[0][0] == ["steam", "-silent"]
    assert placer.asked == [("steam", "DP-3", "maximize")]
    (ticket,) = placer.book.pending()
    assert ticket.pid == 321
    # ohne Wunsch kein Eintrag; ohne Waechter (place None) startet es trotzdem
    execute({"type": "run", "command": "kate", "place": "none"}, make_ctx(popen=popen,
                                                                         place=placer))
    assert len(placer.asked) == 1
    assert execute({"type": "run", "command": "kate", "place": "left"}, make_ctx(popen=popen)).ok


def test_run_missing_program_drops_wish():
    placer = Placer()
    r = execute({"type": "run", "command": "fehlt", "place": "left"},
                make_ctx(popen=FakePopen(missing=("fehlt",)), place=placer))
    assert not r.ok and placer.asked
    assert placer.book.claim("fehlt", "fehlt", 0) is None


def test_app_focus_places_only_when_starting():
    placer, popen = Placer(), FakePopen()
    ctx = make_ctx(popen=popen, place=placer, focus=lambda app, win="": app == "org.kde.dolphin")
    assert execute({"type": "app_focus", "app_id": "org.kde.dolphin", "screen": "links",
                    "place": "left"}, ctx).ok
    assert placer.asked == [] and popen.calls == []          # lief schon: nur nach vorn
    assert execute({"type": "app_focus", "app_id": "org.kde.kate", "screen": "links",
                    "place": "left"}, ctx).ok
    assert popen.calls[0][0] == ["gtk-launch", "--", "org.kde.kate"]
    assert placer.asked == [("org.kde.kate", "links", "left")]
    hit = placer.book.claim("org.kde.kate", "org.kde.kate", 1)
    assert hit.reply() == {"screen": "left", "place": "left"}
