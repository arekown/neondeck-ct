"""Dynamische Ordner: offene Fenster als Kacheln, Lautstaerke-Mixer auf den Reglern."""
import numpy as np

from neondeck.actions.audio import Stream
from neondeck.actions.base import Result
from neondeck.core.windows import WindowInfo
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import RotateEvent
from neondeck.engine.dynamic_folders import MAX_TILES, MIXER_REFRESH_S, DynamicSources
from neondeck.engine.encoders import ROTATE_WINDOW_S
from neondeck.engine.painter import BACK_TILE
from neondeck.profile.model import Assignment, ButtonImage
from support.engine_rig import Rig, make_profile

# --- Dynamische Ordner -----------------------------------------------------------------

def field(i):
    return 60 + (i % 4) * 90 + 45, (i // 4) * 90 + 45


class Sources:
    """Ersatz fuer pactl/.desktop: synchron, zaehlt Abfragen."""

    def __init__(self, streams=()):
        self.streams = list(streams)
        self.stream_calls = 0
        self.icon_calls = 0

    def make(self):
        def streams():
            self.stream_calls += 1
            return list(self.streams)

        def icons():
            self.icon_calls += 1
            return {"org.kde.konsole": "theme:utilities-terminal"}

        return DynamicSources(streams=streams, app_icons=icons, spawn=lambda fn: fn())


def dyn_profile():
    p = make_profile()
    page = p.workspaces[0].touch_pages[0]
    page.buttons[1] = Assignment({"type": "dynamic_folder", "kind": "windows"},
                                 ButtonImage(text="Fenster"))
    page.buttons[2] = Assignment({"type": "dynamic_folder", "kind": "mixer"},
                                 ButtonImage(text="Mixer"))
    return p


def windows(n):
    return [WindowInfo("org.kde.konsole" if i % 2 == 0 else "firefox",
                       "org.kde.konsole" if i % 2 == 0 else "",
                       f"Fenster Nummer {i} mit einem sehr langen Titel — Konsole", 100 + i,
                       f"{{w{i}}}") for i in range(n)]


def test_dynamic_windows_folder_tiles():
    src = Sources()
    loaded = []
    rig = Rig(dyn_profile(), dynamic_sources=src.make(),
              icon_loader=lambda ref, size: loaded.append(ref) or None)
    rig.engine.set_windows(windows(13))
    rig.engine.redraw_all()
    rig.tap(*field(1))
    view = rig.engine.view_state()
    assert view["folder"] == "dynamic:windows" and view["folder_stack"] == ["p1"]
    assert rig.ex.calls == [] and src.icon_calls == 1
    e = rig.engine
    assert e.controls.tile(0) is BACK_TILE
    tiles = [e.controls.tile(i) for i in range(1, 12)]
    assert MAX_TILES == 11 and all(t is not None for t in tiles)  # erste 11 von 13
    assert tiles[0].action == {"type": "app_focus", "app_id": "org.kde.konsole",
                               "window": "{w0}"}
    assert tiles[1].action == {"type": "app_focus", "app_id": "firefox", "window": "{w1}"}
    assert tiles[0].image.text.startswith("Fenster Nummer 0") and len(tiles[0].image.text) <= 24
    assert "Konsole" not in tiles[0].image.text                   # App-Name abgeschnitten
    assert tiles[0].image.icon == "theme:utilities-terminal"      # aus der .desktop-Datei
    assert tiles[1].image.icon == "theme:firefox"                 # sonst resourceClass
    assert "theme:utilities-terminal" in loaded
    # Tippen fokussiert das Fenster
    rig.tap(*field(2))
    assert rig.ex.calls[-1][:2] == (ControlRef("touch", 2), tiles[1].action)
    # Liste aendert sich, waehrend der Ordner offen ist
    before = rig.count(Display.CENTER)
    rig.engine.set_windows(windows(1))
    assert e.controls.tile(1).action["window"] == "{w0}" and e.controls.tile(2) is None
    assert rig.count(Display.CENTER) > before
    # keine Seitenpunkte, kein Wischen; Zurueck fuehrt auf die Ausgangsseite
    rig.tap(field(5)[0], field(5)[1], x_up=field(5)[0] - 200)
    assert rig.engine.view_state()["folder"] == "dynamic:windows"
    rig.tap(*field(0))
    assert rig.engine.view_state()["folder"] is None and rig.engine.page_index == 0
    assert rig.engine.controls.tile(1).action["type"] == "dynamic_folder"


def test_dynamic_folder_left_by_navigation():
    p = dyn_profile()
    rig = Rig(p, dynamic_sources=Sources().make())
    rig.tap(*field(1))
    rig.engine.call("workspace", {"id": "ws2"})
    assert rig.engine.view_state()["folder"] is None
    rig.engine.call("workspace", {"id": "ws1"})
    rig.tap(*field(1))
    rig.engine.call("page_next", {})
    assert rig.engine.view_state()["folder"] is None
    rig.tap(*field(1))
    rig.engine.set_profile(dyn_profile())
    assert rig.engine.view_state()["folder"] is None
    rig.engine.call("dynamic_folder", {"kind": "gibtsnicht"})
    assert rig.engine.view_state()["folder"] is None


def test_mixer_folder_encoders():
    src = Sources([Stream(13751, "Spotify", 28, False, "spotify-client"),
                   Stream(15637, "Video", 100, True, "")])
    later = []
    rig = Rig(dyn_profile(), dynamic_sources=src.make(),
              call_later=lambda delay, fn: later.append((delay, fn)))
    rig.engine.redraw_all()
    left_normal = rig.last(Display.LEFT)
    rig.tap(*field(2))
    e = rig.engine
    assert e.view_state()["folder"] == "dynamic:mixer" and src.stream_calls == 1
    t1, t2 = e.controls.tile(1), e.controls.tile(2)
    assert t1.action == {"type": "stream_mute", "index": 13751}
    assert t1.image.text == "Spotify 28%" and t1.image.icon == "theme:spotify-client"
    assert t2.image.text == "Video stumm" and t2.image.bg != t1.image.bg
    assert e.controls.tile(3) is None
    # Regler 1-6 regeln die ersten sechs Anwendungen; Leisten zeigen Name und Lautstaerke
    assert e.controls.encoder(0).rotate == {"type": "stream_volume", "index": 13751}
    assert e.controls.encoder(1).press == {"type": "stream_mute", "index": 15637}
    assert e.controls.encoder(2).rotate is None
    assert e.painter.strip_section(0, rig.clock()) == ("Spotify", None, 28.0)
    assert e.painter.strip_section(1, rig.clock()) == ("Video", "stumm", None)
    assert not np.array_equal(rig.last(Display.LEFT), left_normal)
    rig.engine.handle(RotateEvent(1, 2))  # Regler 1 (Code 1), zwei Rastungen
    for delay, fn in [x for x in later if x[0] == ROTATE_WINDOW_S]:
        later.remove((delay, fn))
        fn()
    assert rig.ex.calls[-1][:3] == (ControlRef("knob", 0),
                                    {"type": "stream_volume", "index": 13751}, 2)
    # nach jeder Aenderung neu einlesen
    src.streams[0] = Stream(13751, "Spotify", 32, False, "spotify-client")
    rig.ex.finish(result=Result(True, "32 %", value=32.0))
    assert src.stream_calls == 2 and e.controls.tile(1).image.text == "Spotify 32%"
    rig.tap(*field(1))
    assert rig.ex.calls[-1][1] == {"type": "stream_mute", "index": 13751}
    # alle 2 s, solange offen
    ticks = [fn for delay, fn in later if delay == MIXER_REFRESH_S and fn != e.refresh]
    assert MIXER_REFRESH_S == 2.0 and ticks
    ticks[-1]()
    assert src.stream_calls == 3
    # Zurueck: Regler wieder die des Arbeitsbereichs, Takt endet
    rig.ex.finish(result=Result(True))
    calls = src.stream_calls
    rig.tap(*field(0))
    assert e.controls.encoder(0).rotate == {"type": "volume"}
    for delay, fn in list(later):
        if delay == MIXER_REFRESH_S:
            fn()
    assert src.stream_calls == calls
    assert np.array_equal(rig.last(Display.LEFT), left_normal)


def test_mixer_refresh_off_thread_and_coalesced():
    """pactl laeuft ueber ``spawn`` (Thread); waehrend eine Abfrage laeuft, wird keine
    zweite gestartet, das Ergebnis kommt ueber ``post`` zurueck."""
    pending = []
    src = Sources([Stream(1, "A", 50, False, "")])
    sources = src.make()
    sources.spawn = pending.append
    rig = Rig(dyn_profile(), dynamic_sources=sources)
    rig.tap(*field(2))
    assert len(pending) == 1 and src.stream_calls == 0 and rig.engine.controls.tile(1) is None
    pending.pop(0)()
    assert rig.engine.controls.tile(1).image.text == "A 50%"
    rig.engine.handle(RotateEvent(1, 1))
    rig.ex.finish(result=Result(True, "52 %", value=52.0))
    assert len(pending) == 1
    rig.engine.handle(RotateEvent(1, 1))
    rig.ex.finish(result=Result(True, "54 %", value=54.0))
    assert len(pending) == 1                     # laeuft schon: nicht doppelt
    src.streams = [Stream(1, "A", 54, False, "")]
    pending.pop(0)()
    assert len(pending) == 1                     # Nachzuegler holt die zweite Aenderung
    pending.pop(0)()
    assert src.stream_calls == 3 and rig.engine.controls.tile(1).image.text == "A 54%"
    # geschlossen, waehrend eine Abfrage laeuft: das Ergebnis aendert nichts mehr
    rig.engine.handle(RotateEvent(1, 1))
    rig.ex.finish(result=Result(True, "56 %", value=56.0))
    rig.tap(*field(0))
    pending.pop(0)()
    assert rig.engine.view_state()["folder"] is None and pending == []


def mixer_rig(streams, later):
    src = Sources(streams)
    rig = Rig(dyn_profile(), dynamic_sources=src.make(),
              call_later=lambda delay, fn: later.append((delay, fn)))
    rig.tap(*field(2))
    return rig, src


def run_ticks(rig, later):
    """Faellige Mixer-Takte ausfuehren (nicht die Neuzeichnen-Rueckrufe der Engine)."""
    ticks = [x for x in later if x[0] == MIXER_REFRESH_S and x[1] != rig.engine.refresh]
    for x in ticks:
        later.remove(x)
        x[1]()


def test_mixer_polling_paused_while_dark_or_disconnected():
    later = []
    rig, src = mixer_rig([Stream(1, "A", 50, False, "")], later)
    assert src.stream_calls == 1
    run_ticks(rig, later)
    assert src.stream_calls == 2
    rig.engine.lock()
    run_ticks(rig, later)
    run_ticks(rig, later)
    assert src.stream_calls == 2          # gesperrt: kein pactl, der Takt laeuft weiter
    rig.engine.unlock()
    assert src.stream_calls == 3          # einmal nachlesen
    run_ticks(rig, later)
    assert src.stream_calls == 4
    rig.engine.power.sleep_display()
    run_ticks(rig, later)
    assert src.stream_calls == 4
    rig.engine.wake()
    assert src.stream_calls == 5
    rig.engine.device_connected = False
    rig.engine.reset_input()
    run_ticks(rig, later)
    assert src.stream_calls == 5
    rig.engine.device_connected = True
    rig.engine.redraw_all()               # wie nach dem Wiederverbinden
    assert src.stream_calls == 6
    rig.engine.redraw_all()               # ohne ausgefallenen Takt: nichts
    assert src.stream_calls == 6


def test_mixer_knob_pending_dropped_when_streams_shift():
    later = []
    rig, src = mixer_rig([Stream(1, "A", 50, False, ""), Stream(2, "B", 50, False, ""),
                          Stream(3, "C", 50, False, "")], later)
    rig.engine.handle(RotateEvent(2, 1))  # Regler 2 = Stream B, noch gesammelt
    src.streams = [Stream(2, "B", 50, False, ""), Stream(3, "C", 50, False, "")]
    run_ticks(rig, later)                 # Liste rutscht: Regler 2 regelt jetzt C
    assert rig.engine.controls.encoder(1).rotate == {"type": "stream_volume", "index": 3}
    for x in [x for x in later if x[0] == ROTATE_WINDOW_S]:
        later.remove(x)
        x[1]()
    assert [c for c in rig.ex.calls if c[1].get("type") == "stream_volume"] == []
    rig.engine.handle(RotateEvent(2, 1))  # danach wieder normal
    for x in [x for x in later if x[0] == ROTATE_WINDOW_S]:
        x[1]()
    assert rig.ex.calls[-1][1] == {"type": "stream_volume", "index": 3}


def test_late_mixer_result_not_shown_on_workspace_knob():
    later = []
    rig, src = mixer_rig([Stream(1, "A", 50, False, "")], later)
    rig.engine.trigger(ControlRef("knob", 0), {"type": "stream_volume", "index": 1}, steps=1)
    rig.tap(*field(0))                    # Mixer verlassen, Ergebnis kommt spaeter
    rig.ex.finish(result=Result(True, "52 %", value=52.0))
    assert rig.engine.painter.strip_section(0, rig.clock())[1] is None
    rig.engine.trigger(ControlRef("knob", 0), {"type": "volume"}, steps=1)
    rig.ex.finish(result=Result(True, "40 %", value=40.0))  # eigene Ergebnisse zeigen weiter Werte
    assert rig.engine.painter.strip_section(0, rig.clock())[1] == "40 %"
