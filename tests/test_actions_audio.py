"""Audio-Aktionen: Mikrofon stumm, Ausgabe wechseln, Streams einzelner Programme."""
import json

from neondeck.actions import execute
from neondeck.actions.audio import Stream, list_streams
from neondeck.actions.base import Result
from support.fakes import FakeRun, make_ctx

# --- Audio -----------------------------------------------------------------------------

def test_mic_mute_cmd():
    run = FakeRun()
    assert execute({"type": "mic_mute"}, make_ctx(run)).ok
    assert run.calls == [["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"]]
    assert not execute({"type": "mic_mute"}, make_ctx(FakeRun({"pactl": (1, "")}))).ok


SINKS = ("55\talsa_output.hdmi\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
         "61\talsa_output.speaker\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
         "65\talsa_output.razer\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n")


def test_audio_output_cycles():
    for current, want in (("alsa_output.speaker", "alsa_output.razer"),
                          ("alsa_output.razer", "alsa_output.hdmi"),      # im Kreis
                          ("unbekannt", "alsa_output.hdmi")):
        run = FakeRun({"list short sinks": (0, SINKS), "get-default-sink": (0, current + "\n")})
        r = execute({"type": "audio_output_next"}, make_ctx(run))
        assert r == Result(True, want)
        assert run.calls == [["pactl", "list", "short", "sinks"], ["pactl", "get-default-sink"],
                             ["pactl", "set-default-sink", want]]
    r = execute({"type": "audio_output_next"},
                make_ctx(FakeRun({"list short sinks": (0, ""), "get-default-sink": (0, "x")})))
    assert not r.ok and "Audioausgang" in r.message


SINK_INPUTS = json.dumps([
    {"index": 13751, "mute": False, "volume": {"aux0": {"value_percent": "28%"},
                                               "aux1": {"value_percent": "28%"}},
     "properties": {"application.name": "Spotify", "application.icon_name": "spotify-client",
                    "media.name": "Spotify"}},
    {"index": 15637, "mute": True, "volume": {"front-left": {"value_percent": "100%"}},
     "properties": {"media.name": "Video", "node.name": "firefox"}},
    {"index": 9, "volume": {}, "properties": {"application.process.binary": "mpv"}},
])


def test_list_streams_and_stream_actions():
    run = FakeRun({"list sink-inputs": (0, SINK_INPUTS)})
    assert list_streams(run) == [Stream(13751, "Spotify", 28, False, "spotify-client"),
                                 Stream(15637, "Video", 100, True, ""),
                                 Stream(9, "Stream 9", 0, False, "mpv")]
    assert run.calls == [["pactl", "-f", "json", "list", "sink-inputs"]]
    assert list_streams(FakeRun({"list sink-inputs": (0, "kein json")})) == []
    assert list_streams(FakeRun({"list sink-inputs": (1, "")})) == []
    run = FakeRun({"list sink-inputs": (0, SINK_INPUTS)})
    r = execute({"type": "stream_volume", "index": 13751}, make_ctx(run), steps=3)
    assert run.calls[0] == ["pactl", "set-sink-input-volume", "13751", "+6%"]
    assert r == Result(True, "28 %", value=28.0)
    run = FakeRun({"list sink-inputs": (0, SINK_INPUTS)})
    r = execute({"type": "stream_volume", "index": 15637}, make_ctx(run), steps=-1)
    assert run.calls[0] == ["pactl", "set-sink-input-volume", "15637", "-2%"]
    assert r == Result(True, "stumm", muted=True)
    run = FakeRun()
    assert execute({"type": "stream_mute", "index": 13751}, make_ctx(run)).ok
    assert run.calls == [["pactl", "set-sink-input-mute", "13751", "toggle"]]
    assert not execute({"type": "stream_mute", "index": "x; rm"}, make_ctx(FakeRun())).ok
