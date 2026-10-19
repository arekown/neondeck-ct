"""Scrollen/Zoomen per Drehschritt (uinput-Maus), Wiederholen ueber MPRIS,
Bildschirmfoto des aktiven Fensters, Konsole-Titel bei „Befehl ausführen“."""
from evdev import ecodes

from neondeck.actions import execute
from neondeck.actions.mouse import CAPABILITIES, Mouse
from neondeck.desktop.mpris import Mpris, next_loop
from support.fake_dbus import FakeSignalBus
from support.fakes import FakeKeyboard, FakeMouse, FakePopen, make_ctx
from test_states import BRAVE, SPOTIFY, FakeCaller


class FakeUInput:
    def __init__(self):
        self.events = []

    def write(self, etype, code, value):
        self.events.append((etype, code, value))

    def syn(self):
        self.events.append("syn")


def test_mouse_writes_one_event_per_detent():
    dev = FakeUInput()
    m = Mouse(dev, sleep=lambda s: None)
    m.scroll(vertical=-2, horizontal=1)
    rel = ecodes.EV_REL
    assert dev.events == [(rel, ecodes.REL_WHEEL, -1), "syn", (rel, ecodes.REL_WHEEL, -1), "syn",
                          (rel, ecodes.REL_HWHEEL, 1), "syn"]
    # libinput nimmt das Geraet nur mit X/Y und Maustasten als Zeigegeraet
    assert {ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL, ecodes.REL_HWHEEL} \
        <= set(CAPABILITIES[rel]) and ecodes.BTN_LEFT in CAPABILITIES[ecodes.EV_KEY]


def test_scroll_directions_and_steps():
    log = []
    ctx = make_ctx(mouse=FakeMouse(log), keyboard=FakeKeyboard(log))
    assert execute({"type": "scroll"}, ctx, steps=2).ok           # rechts = nach unten
    assert execute({"type": "scroll", "lines": 3, "invert": True}, ctx, steps=1).ok
    assert execute({"type": "scroll", "direction": "horizontal"}, ctx, steps=-1).ok
    assert execute({"type": "scroll"}, ctx, steps=0).ok
    assert log == [("scroll", -2, 0), ("scroll", 3, 0), ("scroll", 0, -1)]


def test_scroll_with_ctrl_is_zoom():
    log = []
    ctx = make_ctx(mouse=FakeMouse(log), keyboard=FakeKeyboard(log))
    assert execute({"type": "scroll", "keys": "KEY_LEFTCTRL", "invert": True}, ctx, steps=1).ok
    assert log == [("press", "KEY_LEFTCTRL"), ("scroll", 1, 0), ("release", "KEY_LEFTCTRL")]
    r = execute({"type": "scroll"}, make_ctx(), steps=1)
    assert not r.ok and "Maus" in r.message


def test_media_loop_action_uses_service():
    calls = []
    assert execute({"type": "media", "key": "loop"},
                   make_ctx(media_loop=lambda p: calls.append(p))).ok
    assert calls == [""]
    assert execute({"type": "media", "key": "loop", "player": "spotify"},
                   make_ctx(media_loop=lambda p: calls.append(p))).ok
    assert calls == ["", "spotify"]
    r = execute({"type": "media", "key": "loop"}, make_ctx())
    assert not r.ok and "MPRIS" in r.message


def test_media_with_player_goes_to_mpris_not_keys():
    sent = []
    ctx = make_ctx(media_control=lambda method, player: sent.append((method, player)))
    for key in ("play_pause", "next", "previous"):
        assert execute({"type": "media", "key": key, "player": "spotify"}, ctx).ok
    assert sent == [("PlayPause", "spotify"), ("Next", "spotify"), ("Previous", "spotify")]


def test_mpris_control_prefers_named_player():
    caller = FakeCaller()
    m = Mpris(bus=FakeSignalBus(), caller=caller, call_later=lambda d, fn: None)
    assert not m.control("Next", "spotify")  # nicht gestartet
    m.start()
    caller.reply("ListNames", [[BRAVE, SPOTIFY]])
    caller.reply("Get", ["Playing"], BRAVE)
    caller.reply("Get", ["Paused"], SPOTIFY)
    assert m.control("PlayPause", "spotify")  # Spotify, obwohl Brave spielt
    service, _path, iface, method, args, _done = caller.calls[-1]
    assert (service, iface, method, args) == (SPOTIFY, "org.mpris.MediaPlayer2.Player",
                                              "PlayPause", [])
    assert m.control("Next", "gibtsnicht")  # unbekannt: der spielende
    assert caller.calls[-1][0] == BRAVE
    m.stop()


def test_mpris_cycles_loop_status_of_playing_or_last_player():
    assert [next_loop(s) for s in ("None", "Playlist", "Track", "?")] == [
        "Playlist", "Track", "None", "Playlist"]
    caller = FakeCaller()
    m = Mpris(bus=FakeSignalBus(), caller=caller, call_later=lambda d, fn: None)
    assert not m.cycle_loop()  # nicht gestartet / keine Player
    m.start()
    caller.reply("ListNames", [[BRAVE, SPOTIFY]])
    caller.reply("Get", ["Paused"], BRAVE)
    caller.reply("Get", ["Playing"], SPOTIFY)
    assert m.loop_target() == SPOTIFY
    assert m.cycle_loop()
    get = caller.calls[-1]
    assert get[0] == SPOTIFY and get[3] == "Get" and get[4][1] == "LoopStatus"
    caller.reply("Get", ["Track"], SPOTIFY)
    service, _path, iface, method, args, _done = caller.calls[-1]
    assert (service, iface, method) == (SPOTIFY, "org.freedesktop.DBus.Properties", "Set")
    assert args[:2] == ["org.mpris.MediaPlayer2.Player", "LoopStatus"]
    assert args[2].variant() == "None"
    caller.reply("Set", [], SPOTIFY)
    # Spotify pausiert: der zuletzt spielende bleibt das Ziel, nicht der erste pausierte
    m._on_status(SPOTIFY, ["Paused"])
    assert m.loop_target() == SPOTIFY
    # Player kann kein Wiederholen: nur Log, kein Set
    m.cycle_loop()
    caller.reply("Get", None, SPOTIFY)
    assert caller.calls == []
    m.stop()


def test_screenshot_window_and_command_title():
    popen = FakePopen()
    assert execute({"type": "kde", "name": "screenshot_window"}, make_ctx(popen=popen)).ok
    assert popen.calls[-1][0] == ["spectacle", "-a", "-b"]
    assert execute({"type": "command", "command": "ssh 192.0.2.10", "title": "Server; 1"},
                   make_ctx(popen=popen)).ok
    assert popen.calls[-1][0] == ["konsole", "-p", "tabtitle=Server, 1",
                                  "-p", "RemoteTabTitleFormat=Server, 1",
                                  "-e", "bash", "-lc", "ssh 192.0.2.10"]
