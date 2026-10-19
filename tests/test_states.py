"""Zustaende: manuell, extern, Stumm (pactl), Medien (MPRIS), App laeuft (KWin-Liste).

Nur Fakes: kein echtes pactl, kein echter D-Bus."""
from neondeck.core.windows import WindowInfo
from neondeck.desktop.audio_state import AudioState
from neondeck.desktop.mpris import Mpris
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent
from neondeck.profile.model import Assignment, ButtonImage, StateDef, TouchPage
from support.engine_rig import TILE5, Rig, make_profile
from support.fake_dbus import FakeSignalBus
from support.fake_process import FakeProcess

T5 = ControlRef("touch", 5)
CENTER5 = (90 + 45, 90 + 2)  # (y, x): linker Rand von Feld 5 (Hintergrundfarbe)
BLACK, RED, GREEN = (0, 0, 0), (0xF8, 0, 0), (0, 0xFC, 0)
A = {"type": "run", "command": "grund"}
S0 = {"type": "run", "command": "zustand0"}


def two_states(source, first_action=None, **extra):
    return Assignment(A, ButtonImage(bg="#000000"),
                      states=[StateDef(ButtonImage(bg="#ff0000"), first_action),
                              StateDef(ButtonImage(bg="#00ff00"))],
                      state_source={"type": source, **extra} if source else None)


def rig_with(tile, pages=1):
    p = make_profile()
    ws = p.workspaces[0]
    ws.touch_pages[0].buttons[5] = tile
    for i in range(1, pages):
        ws.touch_pages.append(TouchPage(f"p{i + 1}", f"Seite {i + 1}"))
    rig = Rig(p)
    rig.engine.redraw_all()
    return rig


def color(rig):
    return tuple(int(c) for c in rig.last(Display.CENTER)[CENTER5])


def commands(rig):
    return [a.get("command") for _r, a, _s, _p in rig.ex.calls]


# --- manuell / extern ------------------------------------------------------------------

def test_manual_state_cycles_and_persists_page_change():
    rig = rig_with(two_states("manual", first_action=S0), pages=2)
    assert color(rig) == RED and rig.engine.controls.state_of(T5) == 0  # beginnt bei Zustand 0
    rig.tap(*TILE5)
    assert commands(rig) == ["zustand0"]  # Aktion des aktuellen Zustands
    assert color(rig) == GREEN and rig.engine.controls.state_of(T5) == 1
    rig.engine.call("page_next", {})
    assert rig.engine.controls.state_of(T5) is None  # andere Seite, anderes Feld
    rig.engine.call("page_previous", {})
    assert color(rig) == GREEN and rig.engine.controls.state_of(T5) == 1  # bleibt ueber Seitenwechsel
    rig.tap(*TILE5)
    assert commands(rig) == ["zustand0", "grund"]  # Zustand 1 ohne Aktion: Grundaktion
    assert color(rig) == RED and rig.engine.controls.state_of(T5) == 0  # zyklisch zurueck


def test_manual_state_on_square_button():
    p = make_profile()
    p.square[15] = two_states("manual", first_action=S0)
    rig = Rig(p)
    for _ in range(3):
        rig.engine.handle(ButtonEvent(15, True))
        rig.engine.handle(ButtonEvent(15, False))
    assert commands(rig) == ["zustand0", "grund", "zustand0"]
    assert rig.engine.controls.state_of(ControlRef("square", 0)) == 1


def test_manual_state_survives_profile_edit_and_workspace_switch():
    rig = rig_with(two_states("manual"))
    rig.tap(*TILE5)
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("workspace", {"id": "ws1"})
    rig.engine.set_profile(rig.engine.profile, keep_view=True)
    assert rig.engine.controls.state_of(T5) == 1 and color(rig) == GREEN


def test_external_state_set():
    rig = rig_with(two_states("external"), pages=2)
    assert color(rig) == BLACK and rig.engine.controls.state_of(T5) is None  # Grundbild bis gesetzt
    rig.tap(*TILE5)
    assert rig.engine.controls.state_of(T5) is None  # Druecken schaltet nicht weiter
    rig.engine.set_state(T5, 1)
    assert color(rig) == GREEN and rig.engine.controls.state_of(T5) == 1
    rig.engine.call("page_next", {})
    rig.engine.call("page_previous", {})
    assert color(rig) == GREEN
    rig.engine.set_state(T5, 0)
    assert color(rig) == RED
    rig.engine.set_state(T5, 9)  # gibt es nicht: Grundbild
    assert color(rig) == BLACK


# --- Stumm (pactl) -------------------------------------------------------------------------

class AudioRig:
    def __init__(self):
        self.procs = []
        self.later = []
        self.events = []
        self.t = 0.0
        self.audio = AudioState(process_factory=lambda: FakeProcess(self.procs),
                                call_later=lambda d, fn: self.later.append((d, fn)),
                                monotonic=lambda: self.t, setpriv=None)
        self.audio.changed.connect(lambda kind, value: self.events.append((kind, value)))

    def running(self, sub):
        return [p for p in self.procs if p.running and p.args[0] == sub]


def test_mute_state_from_pactl_output():
    r = AudioRig()
    r.audio.start()
    sub = r.running("subscribe")[0]
    assert sub.program == "pactl" and sub.env["LC_ALL"] == "C"  # Ausgabe nie uebersetzt
    sink = r.running("get-sink-mute")[0]
    source = r.running("get-source-mute")[0]
    assert sink.args == ["get-sink-mute", "@DEFAULT_SINK@"]
    assert source.args == ["get-source-mute", "@DEFAULT_SOURCE@"]
    sink.exit(0, "Mute: yes\n")
    source.exit(0, "Mute: no\n")
    assert r.events == [("mute", True), ("mic_mute", False)]
    assert r.audio.value("mute") is True and r.audio.value("mic_mute") is False

    # Ereignis am Sink -> nur der Sink wird neu gelesen; Zeile darf geteilt ankommen
    sub.write("Event 'change' on si")
    sub.write("nk #56\nEvent 'change' on sink-input #12\nEvent 'new' on client #3\n")
    assert len(r.running("get-sink-mute")) == 1 and r.running("get-source-mute") == []
    sub.write("Event 'change' on sink #56\n")  # waehrend gelesen wird: einmal nachlesen
    assert len(r.running("get-sink-mute")) == 1
    r.running("get-sink-mute")[0].exit(0, "Mute: yes\n")
    assert r.events == [("mute", True), ("mic_mute", False)]  # unveraendert: keine Meldung
    r.running("get-sink-mute")[0].exit(0, "Mute: no\n")
    assert r.events[-1] == ("mute", False)
    # Standardgeraet gewechselt (server): beide neu lesen
    sub.write("Event 'change' on server #-1\n")
    assert len(r.running("get-sink-mute")) == 1 and len(r.running("get-source-mute")) == 1
    r.running("get-source-mute")[0].exit(0, "Mute: yes\n")
    assert r.events[-1] == ("mic_mute", True)
    r.running("get-sink-mute")[0].exit(1, "Verbindungsfehler\n")  # Fehler: Wert bleibt
    assert r.audio.value("mute") is False

    # Engine: Feld mit Quelle "mute" zeigt Zustand 1 (stumm) bzw. 0
    rig = rig_with(two_states("mute"))
    assert color(rig) == BLACK  # unbekannt: Grundbild
    rig.engine.set_source_value("mute", True)
    assert color(rig) == GREEN
    rig.engine.set_source_value("mute", False)
    assert color(rig) == RED
    rig.tap(*TILE5)
    assert rig.engine.controls.state_of(T5) == 0  # Quelle bestimmt den Zustand, Druecken nicht


def test_pactl_subscribe_restarts_with_backoff_and_stops():
    r = AudioRig()
    r.audio.start()
    r.running("subscribe")[0].exit(1)  # stirbt sofort
    assert [d for d, _ in r.later] == [1.0]
    r.later.pop()[1]()
    assert len(r.running("subscribe")) == 1
    r.running("subscribe")[0].exit(1)
    assert r.later[-1][0] == 2.0  # Wartezeit verdoppelt sich
    r.later.pop()[1]()
    r.t += 120  # lief lange: Wartezeit beginnt wieder bei 1 s
    r.running("subscribe")[0].exit(1)
    assert r.later[-1][0] == 1.0
    r.later.pop()[1]()
    sub = r.running("subscribe")[0]
    r.audio.stop()
    assert sub.killed and not r.running("subscribe")
    assert all(not p.running for p in r.procs)  # auch laufende Lesungen beendet
    assert r.later == []  # kein Neustart nach dem Beenden


# --- Medien (MPRIS) ----------------------------------------------------------------------

class FakeCaller:
    """Ersatz fuer asynchrone D-Bus-Aufrufe: merkt Aufrufe, der Test antwortet."""

    def __init__(self):
        self.calls = []  # (service, path, interface, method, args, done)

    def __call__(self, service, path, interface, method, args, done):
        self.calls.append((service, path, interface, method, list(args), done))

    def reply(self, method, values, service=None):
        for i, c in enumerate(self.calls):
            if c[3] == method and (service is None or c[0] == service):
                del self.calls[i]
                c[5](values)
                return
        raise AssertionError(f"kein offener Aufruf {method} {service}")


class FakeMessage:
    def __init__(self, *args):
        self._args = list(args)

    def arguments(self):
        return self._args


SPOTIFY = "org.mpris.MediaPlayer2.spotify"
BRAVE = "org.mpris.MediaPlayer2.brave.instance1"


def test_media_state_from_mpris():
    bus, caller, later, events = FakeSignalBus(), FakeCaller(), [], []
    m = Mpris(bus=bus, caller=caller, call_later=lambda d, fn: later.append(fn))
    m.changed.connect(events.append)
    assert m.start()
    caller.reply("ListNames", [["org.freedesktop.DBus", BRAVE, SPOTIFY, "org.kde.kwin"]])
    gets = sorted(c[0] for c in caller.calls)
    assert gets == [BRAVE, SPOTIFY]
    assert caller.calls[0][4] == ["org.mpris.MediaPlayer2.Player", "PlaybackStatus"]
    caller.reply("Get", ["Paused"], BRAVE)
    assert m.playing is False and events == [False]
    caller.reply("Get", ["Playing"], SPOTIFY)
    assert m.playing is True and events == [False, True]  # irgendein Player spielt

    # PropertiesChanged: nach kurzer Sammelpause alle Player neu fragen
    for _ in range(3):
        bus.emit("/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties",
                 "PropertiesChanged", FakeMessage("org.mpris.MediaPlayer2.Player", {}, []))
    assert len(later) == 1
    later.pop()()
    caller.reply("Get", ["Paused"], SPOTIFY)
    caller.reply("Get", ["Paused"], BRAVE)
    assert events[-1] is False
    # neuer Player erscheint und spielt, dann verschwindet er
    bus.emit("/org/freedesktop/DBus", "org.freedesktop.DBus", "NameOwnerChanged",
             "org.mpris.MediaPlayer2.vlc", "", ":1.99")
    caller.reply("Get", ["Playing"], "org.mpris.MediaPlayer2.vlc")
    assert events[-1] is True
    bus.emit("/org/freedesktop/DBus", "org.freedesktop.DBus", "NameOwnerChanged",
             "org.mpris.MediaPlayer2.vlc", ":1.99", "")
    assert events[-1] is False and m.playing is False
    assert caller.calls == []
    m.stop()
    assert bus.subscriptions == []

    # Engine: Feld mit Quelle "media"
    rig = rig_with(two_states("media"))
    rig.engine.set_source_value("media", True)
    assert color(rig) == GREEN
    rig.engine.set_source_value("media", False)
    assert color(rig) == RED


# --- App laeuft (KWin-Fensterliste) ----------------------------------------------------------

def test_app_running_state():
    rig = rig_with(two_states("app_running", app="Firefox"))
    assert color(rig) == RED  # keine Fenster: laeuft nicht (Zustand 0)
    rig.engine.set_windows([WindowInfo("kate", "org.kde.kate", "Notizen", 10)])
    assert color(rig) == RED
    rig.engine.set_windows([WindowInfo("kate", "org.kde.kate", "", 10),
                            WindowInfo("firefox", "org.mozilla.firefox", "Seite", 11)])
    assert color(rig) == GREEN and rig.engine.controls.state_of(T5) == 1  # resourceClass, Gross/klein
    rig.engine.set_windows([])
    assert color(rig) == RED


def test_activate_does_not_cycle_when_nothing_ran():
    for live in ({"type": "clock"}, {"type": "stopwatch"}):
        tile = two_states("manual")
        tile.action = live
        rig = rig_with(tile)
        rig.engine.activate(T5, "tap")
        assert rig.engine.controls.state_of(T5) == 0 and rig.ex.calls == []


def test_mpris_list_names_failure_stays_unknown():
    bus, caller, events = FakeSignalBus(), FakeCaller(), []
    m = Mpris(bus=bus, caller=caller, call_later=lambda d, fn: None)
    m.changed.connect(events.append)
    m.start()
    caller.reply("ListNames", None)  # D-Bus-Fehler
    assert m.playing is None and events == []
    m.stop()


def test_pactl_subscribe_dies_with_parent_via_setpriv():
    procs = []
    audio = AudioState(process_factory=lambda: FakeProcess(procs), call_later=lambda d, f: None,
                       setpriv="/usr/bin/setpriv")
    audio.start()
    sub = procs[0]
    assert sub.program == "/usr/bin/setpriv"
    assert sub.args == ["--pdeathsig", "TERM", "--", "pactl", "subscribe"]
    assert [p.program for p in procs[1:]] == ["pactl", "pactl"]  # kurze Abfragen direkt
    audio.stop()
