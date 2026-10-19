"""JSON-API (Server im Dienst, Client, CLI) – In-Process und offscreen.

Alle Tests benutzen eigene Socket-Namen, nie ``neondeck-ct`` (das gehoert dem laufenden
Dienst des Nutzers).
"""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalSocket

from neondeck import cli
from neondeck.api import protocol
from neondeck.api.client import ApiClient, ApiError
from neondeck.api.protocol import MAX_LINE
from neondeck.api.router import Later
from neondeck.api.server import ApiServer
from neondeck.core.settings import Settings
from neondeck.device.layout import ControlRef, Display
from neondeck.profile.model import Assignment, StateDef, TouchPage
from neondeck.profile.store import ProfileStore
from neondeck.ui.poster import QtPoster
from support.service import OpenConfigFacade, call, no_start, unique_name
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("home")

SRC = Path(__file__).resolve().parents[1] / "src"
SN = "CTTEST00000000000000000001"


class Raw:
    """Roher Socket fuer Protokoll-Tests."""

    def __init__(self, name):
        self.sock = QLocalSocket()
        self.sock.connectToServer(name)
        assert self.sock.waitForConnected(15000)
        self.buf = b""

    def send(self, data: bytes):
        self.sock.write(data)
        self.sock.flush()

    def messages(self) -> list[dict]:
        self.buf += bytes(self.sock.readAll())
        *lines, self.buf = self.buf.split(b"\n")
        return [json.loads(x) for x in lines]

    def connected(self) -> bool:
        return self.sock.state() == QLocalSocket.LocalSocketState.ConnectedState


# --- Server -----------------------------------------------------------------------------

def test_ping_status(api_service, api_client):
    app, _, _ = api_service
    assert call(api_client, "ping") == "pong"
    st = call(api_client, "status")
    assert st == {"connected": False, "serial": None, "profile": "default",
                  "profile_name": app.engine.profile.name, "workspace": app.engine.workspace_id,
                  "page": 0, "folder": None, "folder_stack": [],
                  "theme": "cockpit", "dynamic_mode": True,
                  "locked": False, "display_asleep": False}
    app.device.serial = SN
    app.device.on_state(True)
    assert wait_until(lambda: call(api_client, "status")["connected"])
    assert call(api_client, "status")["serial"] == SN
    diag = call(api_client, "diag")  # P13: Zustand des Dienstes und alle Pruefungen
    assert diag["service"]["connected"] and diag["service"]["serial"] == SN
    assert {"device", "uinput", "firmware", "service"} <= {c["id"] for c in diag["checks"]}


def test_settings_put_display_sleep_and_lock(api_service, api_client):
    app, _, _ = api_service
    s = call(api_client, "settings.put", {"display_sleep_min": 30, "lock_with_session": False})
    assert s["display_sleep_min"] == 30 and s["lock_with_session"] is False
    assert app.engine.power.display_sleep_min == 30
    assert Settings.load().display_sleep_min == 30 and Settings.load().lock_with_session is False
    for bad in ({"display_sleep_min": -1}, {"display_sleep_min": "5"},
                {"display_sleep_min": True}, {"display_sleep_min": 1441},
                {"lock_with_session": "nein"}):
        with pytest.raises(ApiError):
            call(api_client, "settings.put", bad)
    assert Settings.load().display_sleep_min == 30


def test_unknown_method_and_bad_params(api_client):
    with pytest.raises(ApiError, match="Unbekannte Methode"):
        call(api_client, "gibtsnicht")
    with pytest.raises(ApiError, match="Bedienelement"):
        call(api_client, "trigger", {"ref": "foo:1"})
    with pytest.raises(ApiError, match="Profil"):
        call(api_client, "profile.get", {"id": "../settings"})


def _profile_with_nav(app):
    """Aktives Profil: zwei Seiten, Feld 0 = naechste Seite, Feld 1 = Seite 0."""
    p = app.engine.profile
    ws = p.workspaces[0]
    while len(ws.touch_pages) < 2:
        ws.touch_pages.append(TouchPage(f"p{len(ws.touch_pages) + 1}", "Zwei"))
    ws.touch_pages[0].buttons[0] = Assignment({"type": "page_next"})
    ws.touch_pages[1].buttons[1] = Assignment({"type": "page", "index": 0})
    return p


def test_profile_put_saves_and_applies(api_service, api_client, home):
    app, _, _ = api_service
    store = ProfileStore(home / "config" / "profiles")
    p = _profile_with_nav(app)
    data = p.to_json()
    assert call(api_client, "profile.put", {"profile": data}) == {"id": "default"}
    assert store.load("default").to_json() == data
    assert app.engine.profile.to_json() == data
    call(api_client, "page", {"dir": "next"})
    assert app.engine.page_index == 1
    data["name"] = "Geändert"
    data["workspaces"][0]["touch_pages"][1]["buttons"][2] = {"action": {"type": "page_next"}}
    call(api_client, "profile.put", {"profile": data})
    assert store.load("default").name == "Geändert"
    assert app.engine.profile.name == "Geändert"
    assert app.engine.page_index == 1  # keep_view: Seite bleibt
    versions = call(api_client, "versions.list", {"id": "default"})
    assert len(versions) == 1 and versions[0]["name"].endswith(".json")  # Snapshot da
    assert store.load("default").name == "Geändert"
    got = call(api_client, "profile.get", {"id": "default"})
    assert got["name"] == "Geändert"
    restored = call(api_client, "versions.restore", {"id": "default", "name": versions[0]["name"]})
    assert restored == {"id": "default"}
    assert app.engine.profile.name != "Geändert" and store.load("default").name != "Geändert"
    # ein kaputter Snapshot (von Hand) wird nicht wiederhergestellt
    vdir = home / "config" / "profiles" / ".versionen" / "default"
    (vdir / "20000101-000000-000000.json").write_text('{"id": "default", "workspaces": []}')
    on_disk = (home / "config" / "profiles" / "default.json").read_bytes()
    with pytest.raises(ApiError, match="ungültig"):
        call(api_client, "versions.restore",
             {"id": "default", "name": "20000101-000000-000000.json"})
    assert (home / "config" / "profiles" / "default.json").read_bytes() == on_disk
    with pytest.raises(ApiError, match="gibt es nicht"):
        call(api_client, "versions.restore", {"id": "default", "name": "fehlt.json"})
    with pytest.raises(ApiError):
        call(api_client, "profile.put", {"profile": "kein Profil"})
    with pytest.raises(ApiError):
        call(api_client, "profile.put", {"profile": dict(data, id="a/b")})


def _center_pixel(app, x, y):
    data = [d for disp, d in app.device.draws if disp is Display.CENTER][-1]
    i = (y * 360 + x) * 2
    return int.from_bytes(data[i:i + 2], "little")


def test_profile_put_rejects_broken_profile(api_service, api_client, home):
    """Kaputtes Profil: Datei bleibt unveraendert, Engine zeichnet weiter, deutscher Fehler."""
    app, _, _ = api_service
    p = _profile_with_nav(app)
    good = p.to_json()
    call(api_client, "profile.put", {"profile": good})
    path = home / "config" / "profiles" / "default.json"
    before = path.read_bytes()
    engine_before = app.engine.profile

    def tile(action):
        d = json.loads(json.dumps(good))
        d["workspaces"][0]["touch_pages"][0]["buttons"][3] = action
        return d

    broken = {
        "leer": {},
        "keine Arbeitsbereiche": dict(good, workspaces=[]),
        "Aktion kein Objekt": tile({"action": "run firefox"}),
        "Farbe kaputt": tile({"action": {"type": "noop"}, "image": {"bg": "#zzzzzz"}}),
    }
    for what, data in broken.items():
        with pytest.raises(ApiError, match="Profil ungültig") as e:
            call(api_client, "profile.put", {"profile": data})
        assert "profil" in str(e.value), what
        assert path.read_bytes() == before, what
        assert app.engine.profile is engine_before, what
    assert call(api_client, "versions.list", {"id": "default"}) == []  # nichts gespeichert
    app.device.draws.clear()
    app.engine.redraw_all()
    assert app.device.draws  # Engine zeichnet weiter
    assert call(api_client, "ping") == "pong"


def test_profile_put_rolls_back_when_engine_fails(api_service, api_client, home, monkeypatch):
    """Scheitert die Uebernahme in die Engine, wird nichts gespeichert."""
    app, _, _ = api_service
    good = app.engine.profile.to_json()
    call(api_client, "profile.put", {"profile": good})
    path = home / "config" / "profiles" / "default.json"
    before = path.read_bytes()
    old = app.engine.profile
    real = app.engine.set_profile

    def failing(profile, keep_view=False):
        if profile is not old:
            raise RuntimeError("kaputt")
        real(profile, keep_view=keep_view)

    monkeypatch.setattr(app.engine, "set_profile", failing)
    with pytest.raises(ApiError, match="nicht anzeigen"):
        call(api_client, "profile.put", {"profile": dict(good, name="Neu")})
    assert path.read_bytes() == before and app.engine.profile is old


def test_profile_put_save_error_keeps_engine(api_service, api_client, home, monkeypatch):
    app, _, _ = api_service
    old = app.engine.profile

    def no_save(profile):
        raise OSError("Platte voll")

    monkeypatch.setattr(app.store, "save", no_save)
    with pytest.raises(ApiError, match="Platte voll"):
        call(api_client, "profile.put", {"profile": dict(old.to_json(), name="Neu")})
    assert app.engine.profile.name == old.name


def test_profile_put_other_profile_only_saves(api_service, api_client, home):
    app, _, _ = api_service
    data = app.engine.profile.to_json()
    data["id"], data["name"] = "zwei", "Zwei"
    call(api_client, "profile.put", {"profile": data})
    assert app.engine.profile.id == "default"
    assert ProfileStore(home / "config" / "profiles").load("zwei").name == "Zwei"


def test_profile_create_list_activate_delete(api_service, api_client):
    app, _, _ = api_service
    call(api_client, "profile.put", {"profile": app.engine.profile.to_json()})
    pid = call(api_client, "profile.create", {"name": "Größe"})["id"]
    assert pid.startswith("groesse-")
    listed = call(api_client, "profile.list")
    assert {(x["id"], x["active"]) for x in listed} == {("default", True), (pid, False)}
    assert {x["id"]: x["name"] for x in listed}[pid] == "Größe"
    call(api_client, "profile.activate", {"id": pid})
    assert app.engine.profile.id == pid and Settings.load().active_profile == pid
    with pytest.raises(ApiError):
        call(api_client, "profile.activate", {"id": "gibtsnicht"})
    call(api_client, "profile.delete", {"id": pid})  # aktiv: erst Wechsel auf default
    assert app.engine.profile.id == "default"
    assert [x["id"] for x in call(api_client, "profile.list")] == ["default"]
    with pytest.raises(ApiError, match="letzte"):
        call(api_client, "profile.delete", {"id": "default"})


def test_view_set_page_trigger_simulate(api_service, api_client):
    app, _, _ = api_service
    p = _profile_with_nav(app)
    call(api_client, "profile.put", {"profile": p.to_json()})
    view = call(api_client, "view.get")
    assert view["page"] == 0 and view["page_count"] == 2
    assert call(api_client, "page", {"index": 1})["page"] == 1
    assert call(api_client, "page", {"dir": "prev"})["page"] == 0
    with pytest.raises(ApiError):
        call(api_client, "page", {"index": 5})
    with pytest.raises(ApiError):
        call(api_client, "page", {"dir": "seitwaerts"})
    call(api_client, "view.set", {"workspace": view["workspace"], "page": 1})
    assert app.engine.page_index == 1
    with pytest.raises(ApiError):
        call(api_client, "view.set", {"workspace": "gibtsnicht"})
    call(api_client, "trigger", {"ref": "touch:1", "which": "tap"})  # Seite 1, Feld 1: Seite 0
    assert app.engine.page_index == 0
    call(api_client, "trigger", {"ref": "touch:0"})  # which = tap
    assert app.engine.page_index == 1
    with pytest.raises(ApiError, match="Keine Aktion"):
        call(api_client, "trigger", {"ref": "touch:5", "which": "double"})
    with pytest.raises(ApiError):
        call(api_client, "trigger", {"ref": "touch:0", "which": "wischen"})
    # simulierte Beruehrung von Feld 1 auf Seite 1
    for down in (True, False):
        call(api_client, "simulate", {"event": {"type": "touch", "finger": 1, "x": 60 + 135,
                                            "y": 45, "down": down}})
    assert app.engine.page_index == 0
    with pytest.raises(ApiError):
        call(api_client, "simulate", {"event": {"type": "button"}})


def test_view_reports_folder_stack(api_service, api_client):
    app, _, _ = api_service
    p = _profile_with_nav(app)
    ws = p.workspaces[0]
    ws.touch_pages[0].buttons[2] = Assignment({"type": "folder", "page": "f1"})
    ws.touch_pages.append(TouchPage("f1", "Ordner", folder=True))
    call(api_client, "profile.put", {"profile": p.to_json()})
    view = call(api_client, "view.get")
    assert view["folder"] is None and view["folder_stack"] == []
    call(api_client, "trigger", {"ref": "touch:2"})
    view = call(api_client, "view.get")
    assert view["folder"] == "f1" and view["folder_stack"] == ["p1"] and view["page"] == 2
    st = call(api_client, "status")
    assert st["folder"] == "f1" and st["folder_stack"] == ["p1"]
    view = call(api_client, "view.set", {"workspace": ws.id, "page": 1})  # normale Seite
    assert view["folder"] is None and view["folder_stack"] == [] and view["page"] == 1


def test_image_and_state_set(api_service, api_client, tmp_path):
    app, _, _ = api_service
    png = tmp_path / "blau.png"
    Image.new("RGB", (40, 40), (0, 0, 255)).save(png)
    app.device.draws.clear()
    assert call(api_client, "image.set", {"ref": "touch:0", "path": str(png)}) == {}
    data = [d for disp, d in app.device.draws if disp is Display.CENTER][-1]
    px = int.from_bytes(data[(45 * 360 + 45) * 2:(45 * 360 + 45) * 2 + 2], "little")
    assert px == 0x001F  # Feld 0 blau (RGB565)
    with pytest.raises(ApiError, match="Touch"):
        call(api_client, "image.set", {"ref": "round:0", "path": str(png)})
    with pytest.raises(ApiError, match="nicht lesbar"):
        call(api_client, "image.set", {"ref": "touch:0", "path": str(tmp_path / "fehlt.png")})
    with pytest.raises(ApiError):
        call(api_client, "image.set", {"ref": "touch:0", "path": "relativ.png"})
    call(api_client, "image.set", {"ref": "touch:0", "path": None})  # aufheben
    assert app.engine.painter.image_override(ControlRef("touch", 0)) is None
    page = app.engine.profile.workspaces[0].touch_pages[0]
    page.buttons[2] = Assignment({}, states=[StateDef(), StateDef()])  # zwei Zustaende
    assert call(api_client, "state.set", {"ref": "touch:2", "n": 1}) == {}
    assert app.engine.controls.state_of(ControlRef("touch", 2)) == 1
    for bad in (-1, "1", True, None):
        with pytest.raises(ApiError):
            call(api_client, "state.set", {"ref": "touch:2", "n": bad})


def test_trigger_like_device_cycles_state_and_key_timing(api_service, api_client):
    app, _, _ = api_service
    page = app.engine.profile.workspaces[0].touch_pages[0]
    page.buttons[3] = Assignment({"type": "hotkey", "keys": ["KEY_A"]},
                                 double={"type": "hotkey", "keys": ["KEY_B"]},
                                 states=[StateDef(), StateDef()],
                                 state_source={"type": "manual"})
    ref = ControlRef("touch", 3)
    assert app.engine.controls.state_of(ref) == 0
    call(api_client, "trigger", {"ref": "touch:3", "which": "double"})
    assert app.engine.controls.state_of(ref) == 0  # nur Tippen schaltet weiter
    call(api_client, "trigger", {"ref": "touch:3"})
    assert app.engine.controls.state_of(ref) == 1
    call(api_client, "trigger", {"ref": "touch:3", "action": {"type": "hotkey", "keys": ["KEY_C"]}})
    assert app.engine.controls.state_of(ref) == 1  # Editor „Testen“ schaltet nicht weiter
    s = call(api_client, "settings.put", {"double_ms": 250, "hold_ms": 800})
    assert (s["double_ms"], s["hold_ms"]) == (250, 800)
    assert (app.engine.input.gestures.double_ms, app.engine.input.gestures.hold_ms) == (250, 800)
    assert Settings.load().hold_ms == 800
    for bad in ({"double_ms": 50}, {"hold_ms": 5000}, {"hold_ms": "600"}, {"double_ms": True}):
        with pytest.raises(ApiError):
            call(api_client, "settings.put", bad)
    assert app.engine.input.gestures.hold_ms == 800


def test_settings_get_put(api_service, api_client):
    app, _, _ = api_service
    s = call(api_client, "settings.get")
    assert s["brightness"] == 8 and s["theme"] == "cockpit"
    assert call(api_client, "settings.put", {"brightness": 4})["brightness"] == 4
    assert app.device.brightness[-1] == 4 and Settings.load().brightness == 4
    levels = next(a for a in app.tray.menu.actions() if a.text() == "Helligkeit").menu()
    assert [a.text() for a in levels.actions() if a.isChecked()] == ["4"]
    call(api_client, "settings.put", {"brightness": 5})  # kein Menueeintrag passt
    assert [a.text() for a in levels.actions() if a.isChecked()] == []
    for bad in ({"brightness": 11}, {"brightness": "4"}, {"gibtsnicht": 1},
                {"theme": "cockpit", "brightness": True}):
        with pytest.raises(ApiError):
            call(api_client, "settings.put", bad)
    assert Settings.load().brightness == 5  # nichts halb uebernommen
    assert call(api_client, "settings.put", {"dynamic_mode": False})["dynamic_mode"] is False
    assert Settings.load().dynamic_mode is False and app.dynamic.enabled is False
    assert call(api_client, "status")["dynamic_mode"] is False
    with pytest.raises(ApiError):
        call(api_client, "settings.put", {"dynamic_mode": "nein"})
    with pytest.raises(ApiError):
        call(api_client, "settings.put", {"last_pages": {}})  # nur intern
    # Profilwechsel scheitert: Fehler, und auch die Helligkeit bleibt
    app.switch_profile = lambda pid: None
    call(api_client, "profile.put", {"profile": dict(app.engine.profile.to_json(), id="zwei")})
    with pytest.raises(ApiError, match="zwei"):
        call(api_client, "settings.put", {"active_profile": "zwei", "brightness": 2})
    assert Settings.load().brightness == 5 and app.engine.profile.id == "default"


def test_open_config_request(api_service, api_client):
    app, _, _ = api_service
    opened = []
    app.open_config = lambda: opened.append(1)
    assert call(api_client, "open_config") == {}
    assert opened == [1]


def test_events_only_to_subscribers(api_service, api_client):
    app, _, name = api_service
    p = _profile_with_nav(app)
    call(api_client, "profile.put", {"profile": p.to_json()})
    other = ApiClient(name)
    assert other.connect_or_start(timeout=1.0, starter=no_start)
    try:
        seen, unseen = [], []
        api_client.event.connect(lambda ev, data: seen.append((ev, data)))
        other.event.connect(lambda ev, data: unseen.append((ev, data)))
        assert call(api_client, "subscribe", {"role": "editor"}) == {"editors": 0}
        call(other, "page", {"dir": "next"})
        assert wait_until(lambda: any(e == "view.changed" for e, _ in seen))
        view = next(d for e, d in seen if e == "view.changed")
        assert view["page"] == 1 and view["profile"] == "default"
        app.device.on_state(True)
        assert wait_until(lambda: ("device.state", {"connected": True, "serial": None}) in seen)
        call(other, "profile.put", {"profile": p.to_json()})
        assert wait_until(lambda: any(e == "profile.changed" for e, _ in seen))
        app.engine.hooks.on_value(ControlRef("knob", 0), "42 %")
        assert wait_until(lambda: ("value", {"ref": "knob:0", "text": "42 %"}) in seen)
        # Antworten und Ereignisse gehen der Reihe nach ueber dieselbe Verbindung: nach dieser
        # Antwort haette ``other`` jedes fruehere Ereignis schon bekommen.
        assert call(other, "ping") == "pong"
        assert unseen == []
    finally:
        other.close()


def test_bad_json_line_ignored_connection_stays(api_service):
    raw = Raw(api_service[2])
    raw.send(b"{kaputt\n")
    raw.send(b"[1, 2]\n")
    raw.send(b'{"id": 7, "method": "ping"}\n')
    got = []
    assert wait_until(lambda: got.extend(raw.messages()) or got)
    assert got == [{"id": 7, "result": "pong"}]
    assert raw.connected()


def test_deeply_nested_json_ignored(api_service):
    raw = Raw(api_service[2])
    raw.send(b"[" * 200_000 + b"\n")
    raw.send(b'{"id": 9, "method": "ping", "params": ' + b"[" * 200_000 + b"]" * 200_000
             + b'}\n{"id": 10, "method": "ping"}\n')
    got = []
    assert wait_until(lambda: got.extend(raw.messages()) or len(got) >= 1)
    assert got[-1] == {"id": 10, "result": "pong"} and raw.connected()


def test_utf8_split_across_writes(api_service, api_client):
    app, _, name = api_service
    raw = Raw(name)
    line = '{"id": 1, "method": "profile.create", "params": {"name": "Größe"}}\n'.encode()
    cut = line.index("ö".encode()) + 1  # mitten im Zeichen
    raw.send(line[:cut])
    server = api_service[1]
    # erst weiter, wenn der Dienst die erste Haelfte (ohne Zeilenende) gelesen hat
    assert wait_until(lambda: any(c.buf.pending == cut for c in server.connections))
    raw.send(line[cut:])
    got = []
    assert wait_until(lambda: got.extend(raw.messages()) or got)
    pid = got[0]["result"]["id"]
    assert {x["id"]: x["name"] for x in call(api_client, "profile.list")}[pid] == "Größe"


def test_request_then_abort_still_processed(api_service):
    app, _, name = api_service
    opened = []
    app.open_config = lambda: opened.append(1)
    sock = QLocalSocket()
    sock.connectToServer(name)
    assert sock.waitForConnected(15000)
    sock.write(b'{"id": 1, "method": "open_config"}\n')
    assert sock.waitForBytesWritten(15000)
    sock.abort()  # bevor der Server gelesen hat
    assert wait_until(lambda: opened)
    assert call_ok(name)


def call_ok(name) -> bool:
    c = ApiClient(name)
    try:
        return c.connect_or_start(timeout=1.0, starter=no_start) and call(c, "ping") == "pong"
    finally:
        c.close()


def test_slow_subscriber_dropped(api_service):
    _, server, name = api_service
    raw = Raw(name)
    raw.send(b'{"id": 1, "method": "subscribe"}\n')
    assert wait_until(lambda: raw.messages() or True) and wait_until(
        lambda: any(c.subscribed for c in server.connections))
    blob = "x" * 100_000
    for _ in range(60):  # 6 MB, ohne dass der Abonnent liest
        server.emit_event("value", {"ref": "knob:0", "text": blob})
    assert not any(c.subscribed for c in server.connections)
    assert call_ok(name)  # der Server bedient andere weiter


def test_large_reply_not_dropped(api_service, api_client):
    """Die Rueckstau-Grenze gilt nur fuer Ereignisse, nicht fuer grosse Antworten."""
    app, _, _ = api_service
    d = app.engine.profile.to_json()
    d["name"] = "n" * 6_000_000
    call(api_client, "profile.put", {"profile": d})
    assert len(call(api_client, "profile.get", {"id": "default"})["name"]) == 6_000_000


def test_request_without_method_gets_error(api_service):
    raw = Raw(api_service[2])
    raw.send(b'{"id": 3}\n{"id": 4, "method": "ping", "params": []}\n')
    got = []
    assert wait_until(lambda: got.extend(raw.messages()) or len(got) == 2)
    assert got[0]["id"] == 3 and "error" in got[0]
    assert got[1]["id"] == 4 and "error" in got[1]


def test_oversize_line_closes(api_service):
    raw = Raw(api_service[2])
    raw.send(b"x" * (MAX_LINE + 1))
    assert wait_until(lambda: not raw.connected())
    again = Raw(api_service[2])  # der Server lebt weiter
    again.send(b'{"id": 1, "method": "ping"}\n')
    got = []
    assert wait_until(lambda: got.extend(again.messages()) or got)
    assert got == [{"id": 1, "result": "pong"}]


def test_client_disconnect_fails_pending_calls(api_service):
    _, server, name = api_service
    c = ApiClient(name)
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    got = []
    c.call("ping", {}, lambda r, e: got.append((r, e)))
    server.close()
    assert wait_until(lambda: got)
    assert got[0][0] is None and "getrennt" in got[0][1]
    with pytest.raises(ApiError):
        c.call("ping", {})
    c.close()


# --- Einzelinstanz -----------------------------------------------------------------------

def test_listen_does_not_steal_running_server():
    name = unique_name()
    first = ApiServer(OpenConfigFacade(), name, poster=QtPoster())
    assert first.listen()
    second = ApiServer(OpenConfigFacade(), name, poster=QtPoster())
    try:
        assert not second.listen()  # laeuft schon: Socket nicht entfernen
        c = ApiClient(name)
        assert c.connect_or_start(timeout=1.0, starter=no_start)
        assert call(c, "ping") == "pong"
        c.close()
    finally:
        second.close()
        first.close()


# --- Client: Dienst starten --------------------------------------------------------------

def test_connect_or_start_launches():
    name = unique_name()
    servers, starts = [], []

    def starter():
        starts.append(time.monotonic())
        # Dienst erscheint verzoegert
        QTimer.singleShot(400, lambda: servers.append(
            ApiServer(OpenConfigFacade(), name, poster=QtPoster())) or
                          servers[-1].listen())

    c = ApiClient(name)
    try:
        t0 = time.monotonic()
        assert c.connect_or_start(timeout=5.0, starter=starter)
        assert len(starts) == 1 and time.monotonic() - t0 >= 0.35
        assert call(c, "ping") == "pong"
        c.close()
        c2 = ApiClient(name)  # laeuft schon: kein zweiter Start
        assert c2.connect_or_start(timeout=1.0, starter=no_start)
        c2.close()
    finally:
        for s in servers:
            s.close()


def test_connect_or_start_gives_up():
    c = ApiClient(unique_name())
    starts = []
    t0 = time.monotonic()
    assert not c.connect_or_start(timeout=0.3, starter=lambda: starts.append(1))
    # gibt nach dem eigenen Zeitlimit auf: nicht frueher, und nicht erst nach dem Standard
    assert starts == [1] and 0.25 <= time.monotonic() - t0 < 5.0


@pytest.mark.real_spawn
def test_default_starter_command(monkeypatch, tmp_path):
    from neondeck.api import client as client_mod
    calls = []
    monkeypatch.setattr(client_mod.proc, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    launcher = tmp_path / "bin" / "neondeck-ct"
    monkeypatch.setattr(client_mod, "launcher_path", lambda: launcher)
    client_mod.start_service()
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(0o755)
    client_mod.start_service()
    (cmd1, kw1), (cmd2, kw2) = calls
    assert cmd1 == [sys.executable, "-m", "neondeck"]
    assert cmd2 == [str(launcher)]
    client_mod.start_editor("ldl-test-x")  # Editor ebenso losgeloest
    cmd3, kw3 = calls[2]
    assert cmd3 == [str(launcher), "--config", "--server", "ldl-test-x"]
    for kw in (kw1, kw2, kw3):
        assert kw["start_new_session"] is True
        assert kw["stdin"] is kw["stdout"] is kw["stderr"] is subprocess.DEVNULL


# --- CLI --------------------------------------------------------------------------------

def _run_cli(args, home, timeout=15.0):
    """CLI als eigener Prozess; die Ereignisschleife hier bedient derweil den Test-Server."""
    env = dict(os.environ, NEONDECK_HOME=str(home), QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=str(SRC))
    proc = subprocess.Popen([sys.executable, "-m", "neondeck", "ctl", *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert wait_until(lambda: proc.poll() is not None, timeout)
    out, err = proc.communicate()
    return proc.returncode, out.decode(), err.decode()


def test_cli_page_next(api_service, api_client, home):
    app, _, name = api_service
    call(api_client, "profile.put", {"profile": _profile_with_nav(app).to_json()})
    code, out, err = _run_cli(["--server", name, "page", "next"], home)
    assert (code, err) == (0, "")
    assert json.loads(out)["page"] == 1 and app.engine.page_index == 1


def test_cli_commands_in_process(api_service, api_client, home, monkeypatch, tmp_path):
    """Uebersetzung Befehl -> Anfrage (ohne Socket, mit aufgezeichneten Aufrufen)."""
    app, _, _ = api_service
    sent = []
    answers = {"profile.list": [{"id": "default", "name": "Standard (CT)"},
                                {"id": "obs-1", "name": "OBS"}],
               "view.get": {"workspaces": [{"id": "ws1", "name": "Allgemein"}]}}

    class FakeClient:
        def __init__(self, name):
            assert name != protocol.SERVER_NAME  # nie der Socket des echten Dienstes
            self.name = name

        def connect(self, timeout):
            return True  # die CLI verbindet nur, sie startet den Dienst nicht

        def call(self, method, params=None, timeout=2.0):
            sent.append((method, params))
            return answers.get(method, {})

        def close(self):
            pass

    monkeypatch.setattr(cli, "BlockingClient", FakeClient)
    name = unique_name()
    monkeypatch.chdir(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    for args in (["status"], ["page", "prev"], ["page", "2"], ["workspace", "allgemein"],
                 ["profile", "obs"], ["profile", "obs-1"], ["press", "knob:2"],
                 ["state", "touch:3", "1"], ["image", "touch:3", "bild.png"]):
        assert cli.main(["--server", name, *args], out=out, err=err) == 0, err.getvalue()
    assert [m for m, _ in sent if m not in ("profile.list", "view.get")] == [
        "status", "page", "page", "view.set", "profile.activate", "profile.activate",
        "trigger", "state.set", "image.set"]
    params = [p for m, p in sent if m not in ("profile.list", "view.get")]
    assert params[1:] == [{"dir": "prev"}, {"index": 2}, {"workspace": "ws1"}, {"id": "obs-1"},
                          {"id": "obs-1"}, {"ref": "knob:2", "which": "tap"},
                          {"ref": "touch:3", "n": 1},
                          {"ref": "touch:3", "path": str(tmp_path / "bild.png")}]
    assert cli.main(["--server", name, "profile", "gibtsnicht"], out=out, err=err) == 1
    assert "gibtsnicht" in err.getvalue()
    # unerwartete Fehler: Meldung statt Traceback, Exit 1
    answers["view.get"] = {"workspaces": [{"name": "ohne id"}]}
    err = io.StringIO()
    assert cli.main(["--server", name, "workspace", "ohne id"], out=out, err=err) == 1
    assert err.getvalue().startswith("Fehler: ") and "Traceback" not in err.getvalue()


def test_cli_unknown_ref_exit_1(home):
    out, err = io.StringIO(), io.StringIO()
    # ungueltige Angaben scheitern vor jedem Verbindungsversuch
    assert cli.main(["--server", unique_name(), "press", "foo:1"], out=out, err=err) == 1
    assert "foo:1" in err.getvalue() and out.getvalue() == ""
    assert cli.main(["--server", unique_name(), "state", "touch:12", "1"], out=out, err=err) == 1
    assert cli.main(["--server", unique_name(), "bloedsinn"], out=out, err=err) == 1
    assert cli.main(["--server", unique_name(), "page"], out=out, err=err) == 1


def test_cli_service_not_running(home):
    out, err = io.StringIO(), io.StringIO()
    assert cli.main(["--server", unique_name(), "status"], out=out, err=err) == 1
    assert "läuft nicht" in err.getvalue()


def test_cli_error_from_service_exit_1(api_service, home):
    code, out, err = _run_cli(["--server", api_service[2], "press", "touch:5"], home)
    assert code == 1 and "Keine Aktion" in err and out == ""


def test_apps_list(api_service, api_client, tmp_path, monkeypatch):
    from neondeck.core import desktop_apps
    apps = tmp_path / "apps"
    apps.mkdir()
    (apps / "org.kde.konsole.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Konsole\nIcon=utilities-terminal\n"
        "Exec=konsole\nStartupWMClass=konsole\n", encoding="utf-8")
    monkeypatch.setattr(desktop_apps, "default_dirs", lambda: [apps])
    assert call(api_client, "apps.list") == [{"id": "org.kde.konsole", "name": "Konsole",
                                          "icon": "utilities-terminal", "wm_class": "konsole",
                                          "exec": "konsole"}]


def _answer(result):
    """Antwort eines Handlers; ein ``Later`` wird mit laufender Ereignisschleife abgewartet."""
    if not isinstance(result, Later):
        return result, None
    got = []
    result.on_done = lambda r, e: got.append((r, e))
    assert wait_until(lambda: got)
    return got[0]


def test_apps_list_cached_and_read_off_gui_thread(monkeypatch):
    import threading

    from neondeck.api.handlers import system
    from neondeck.core import desktop_apps
    calls = []

    def fake_list_apps():
        calls.append(threading.current_thread() is threading.main_thread())
        return [desktop_apps.DesktopApp(f"app{len(calls)}", "A", "", "", "a")]

    monkeypatch.setattr(desktop_apps, "list_apps", fake_list_apps)
    t = [1000.0]
    server = ApiServer(poster=QtPoster(), clock=lambda: t[0])
    apps = server.methods["apps.list"]
    assert _answer(apps(None, {}))[0][0]["id"] == "app1"
    assert calls == [False]                               # nicht im GUI-Thread gelesen
    t[0] += system.APPS_TTL_S - 1
    assert apps(None, {})[0]["id"] == "app1"              # aus dem Zwischenspeicher
    assert len(calls) == 1
    t[0] += 2                                             # abgelaufen: neu lesen
    assert _answer(apps(None, {}))[0][0]["id"] == "app2"
    assert calls == [False, False]


def test_apps_list_parallel_requests_one_read_and_errors(monkeypatch):
    import threading

    from neondeck.core import desktop_apps
    gate = threading.Event()
    calls = []

    def slow():
        calls.append(1)
        gate.wait(15)
        raise OSError("kaputt")

    monkeypatch.setattr(desktop_apps, "list_apps", slow)
    server = ApiServer(poster=QtPoster())
    laters = [server.methods["apps.list"](None, {}) for _ in range(3)]  # warten auf einen
    got = []
    for later in laters:
        later.on_done = lambda r, e: got.append((r, e))
    assert wait_until(lambda: calls)
    gate.set()
    assert wait_until(lambda: len(got) == 3)
    assert len(calls) == 1                                # ein Lesevorgang fuer alle
    assert all(r is None and "kaputt" in e for r, e in got)
    assert server.methods["ping"](None, {}) == "pong"     # Dienst antwortet weiter
