"""Editor als eigener Prozess: ConfigWindow ueber RemoteEngine an der JSON-API.

Alle Tests benutzen eigene Socket-Namen (nie den des laufenden Dienstes des Nutzers);
Dienst und Editor laufen hier im selben Prozess (In-Process-ApiServer), ausser wo ein
echter Kindprozess abstuerzen soll.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from neondeck.api import client as api_client
from neondeck.api import protocol
from neondeck.api.client import ApiClient
from neondeck.api.server import ApiServer
from neondeck.core import paths
from neondeck.core.settings import Settings
from neondeck.device.layout import ControlRef
from neondeck.editor import main as editor_main
from neondeck.editor.editing import commit
from neondeck.editor.remote.engine import RemoteEngine
from neondeck.editor.remote.store import RemoteStore
from neondeck.editor.windows.config_window import ConfigWindow
from neondeck.profile.ids import imported_dir
from neondeck.profile.importers.lp5 import import_lp5
from neondeck.profile.model import Assignment, ButtonImage, Profile, TouchPage
from neondeck.profile.store import ProfileStore
from neondeck.ui import theme
from neondeck.ui.poster import QtPoster
from support.lp5 import make_lp5
from support.service import OpenConfigFacade, Service, no_start, unique_name
from support.waiting import wait_until
from support.window import choose_type

pytestmark = pytest.mark.usefixtures("home", "no_modal_error")

SRC = Path(__file__).resolve().parents[1] / "src"


def assign(win: ConfigWindow, ref: ControlRef, action_type: str) -> None:
    win.select(ref)
    choose_type(win.editor.content.action_form, action_type)
    win.flush()


def saved_round(service, index: int):
    if "default" not in service.store.list():
        return None
    a = service.store.load("default").round.get(protocol_round(index))
    return a.action if a else None


def protocol_round(index: int) -> int:
    from neondeck.device.layout import ROUND_CODES
    return ROUND_CODES[index]


# --- Editor nur ueber die API ------------------------------------------------------------

def test_editor_uses_api_only(editor_service, editor, monkeypatch):
    win = editor.window
    editor_service.store.save(editor_service.app.engine.profile)  # liegt schon auf der Platte
    assert isinstance(win, ConfigWindow) and win.isVisible()
    assert isinstance(win.engine, RemoteEngine) and isinstance(win.store, RemoteStore)
    assert not isinstance(win.store, ProfileStore)
    assert win.engine.profile is not editor_service.app.engine.profile  # eigene Kopie im Editor
    puts = []
    real = editor_service.server.methods["profile.put"]
    editor_service.server.methods["profile.put"] = lambda c, p: puts.append(p) or real(c, p)
    assign(win, ControlRef("round", 0), "mute_toggle")
    assert wait_until(lambda: saved_round(editor_service, 0) == {"type": "mute_toggle"})
    assert puts and puts[-1]["profile"]["id"] == "default"
    engine = editor_service.app.engine
    assert engine.profile.round[protocol_round(0)].action == {"type": "mute_toggle"}
    assert editor_service.store.versions("default")  # Speichern im Dienst: mit Snapshot


def test_editor_follows_device_navigation_and_drives_it(editor_service, editor):
    app, win = editor_service.app, editor.window
    p = app.engine.profile
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Seite 2"))
    app.engine.set_profile(p, keep_view=True)
    app.store.save(p)
    app.emit("profile.changed", {"id": "default", "active": "default"})
    assert wait_until(lambda: len(win.engine.profile.workspaces[0].touch_pages) == 2)
    app.engine.call("page_next", {})  # am Geraet
    assert wait_until(lambda: win.page_bar.tabs.currentIndex() == 1 and win.engine.page_index == 1)
    win.page_bar.tabs.setCurrentIndex(0)  # im Editor
    assert wait_until(lambda: app.engine.page_index == 0)


def test_editor_test_button_triggers_shown_action(editor_service, editor):
    calls = []
    editor_service.app.engine.trigger = \
        lambda ref, action, steps=0: calls.append((ref, action, steps))
    win = editor.window
    win.select(ControlRef("touch", 2))
    choose_type(win.editor.content.action_form, "mute_toggle")  # noch nicht gespeichert
    win.editor.test_button.click()
    assert wait_until(lambda: calls)
    assert calls == [(ControlRef("touch", 2), {"type": "mute_toggle"}, 0)]


def test_editor_sees_changes_from_elsewhere(editor_service, editor):
    app, win = editor_service.app, editor.window
    other = ApiClient(editor_service.name)
    assert other.connect_or_start(timeout=1.0, starter=no_start)
    try:
        d = app.engine.profile.to_json()
        d["name"] = "Von der CLI"
        got = []
        other.call("profile.put", {"profile": d}, lambda r, e: got.append(e))
        assert wait_until(lambda: got) and got == [None]
        assert wait_until(lambda: win.engine.profile.name == "Von der CLI")
        assert wait_until(lambda: win.toolbar.profile_combo.currentText() == "Von der CLI")
    finally:
        other.close()


def test_profile_manager_creates_and_deletes_through_service(editor_service, editor, monkeypatch):
    win = editor.window
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Neu im Editor", True)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    m = win.extras.make_profile_manager()
    try:
        m.new_profile()
        pid = next(i for i in m.profile_ids() if i.startswith("neu-im-editor"))
        assert wait_until(lambda: pid in editor_service.store.list())
        m.select_profile(pid)
        m.delete_profile()
        assert pid not in editor_service.store.list()
        assert pid not in m.profile_ids()
    finally:
        m.deleteLater()


def test_profile_combo_switches_profile_in_service(editor_service, editor):
    app, win = editor_service.app, editor.window
    app.store.save(app.engine.profile)
    app.store.save(Profile.empty("zwei", "Zwei"))
    app.emit("profile.changed", {"id": "zwei", "active": "default"})
    assert wait_until(lambda: win.toolbar.profile_combo.findData("zwei") >= 0)
    win.toolbar.profile_combo.setCurrentIndex(win.toolbar.profile_combo.findData("zwei"))
    assert app.engine.profile.id == "zwei" and win.engine.profile.id == "zwei"
    assert Settings.load().active_profile == "zwei"
    assert win.toolbar.profile_combo.currentData() == "zwei"
    app.engine.call("profile", {"id": "default"})  # am Geraet zurueck: Editor zieht nach
    assert wait_until(lambda: win.toolbar.profile_combo.currentData() == "default")
    assert win.engine.profile.id == "default"


def test_closing_editor_saves_pending_changes(editor_service, editor, monkeypatch):
    monkeypatch.setattr(editor_main, "DRAIN_S", 15.0)  # Obergrenze nur fuer den Fehlerfall
    win = editor.window
    win.select(ControlRef("round", 4))
    choose_type(win.editor.content.action_form, "mute_toggle")  # noch im 300-ms-Puffer
    assert saved_round(editor_service, 4) is None
    win.close()
    assert not win.isVisible()
    assert saved_round(editor_service, 4) == {"type": "mute_toggle"}  # vor dem Ende angekommen


def test_switch_to_broken_profile_shows_message(editor_service, editor, monkeypatch):
    app, win = editor_service.app, editor.window
    app.store.save(Profile.empty("kaputt", "Kaputt"))
    app.emit("profile.changed", {"id": "kaputt", "active": "default"})
    assert wait_until(lambda: win.toolbar.profile_combo.findData("kaputt") >= 0)
    real = app.engine.set_profile

    def broken(profile, **kw):
        if profile.id == "kaputt":
            raise ValueError("Bild zerbrochen")
        return real(profile, **kw)

    monkeypatch.setattr(app.engine, "set_profile", broken)
    win.toolbar.profile_combo.setCurrentIndex(win.toolbar.profile_combo.findData("kaputt"))  # wirft nicht
    assert win.statusBar().currentMessage() == f"{protocol.SHOW_FAILED}: Bild zerbrochen"
    assert win.engine.profile.id == "default" and app.engine.profile.id == "default"
    assert win.toolbar.profile_combo.currentData() == "default"


def test_switch_error_in_local_window_shows_message(home):
    """Auch ohne Dienst (Fenster direkt an einer Engine): Fehler nie in den Qt-Slot."""
    from support.engine_rig import make_engine
    store = ProfileStore(home / "config" / "profiles")
    store.save(Profile.empty())
    store.save(Profile.empty("zwei", "Zwei"))

    def boom(pid):
        raise ValueError("kaputt gezeichnet")

    engine = make_engine(store.load("default"))
    win = ConfigWindow(store, engine, boom)
    try:
        win.navigator.switch_to("zwei")
        assert win.statusBar().currentMessage() == f"{protocol.SHOW_FAILED}: kaputt gezeichnet"
    finally:
        win.deleteLater()


def test_theme_from_service_and_back(editor_service, monkeypatch):
    Settings(theme="neutral").save()
    editor_service.app.settings.theme = "neutral"  # wie geladen, ohne es im Dienst anzuwenden
    ed = editor_main.start(server_name=editor_service.name, starter=no_start, timeout=2.0)
    try:
        assert theme.current().name == "neutral"  # Editor uebernimmt das Theme des Dienstes
        ed.window.theme_menu.set_theme("cockpit", scanlines=True)
        assert wait_until(lambda: Settings.load().theme == "cockpit")
        assert Settings.load().theme_scanlines is True
    finally:
        ed.shutdown()


# --- Verbindung, Absturz, Start ----------------------------------------------------------

def test_editor_survives_service_restart(editor_service, editor):
    win = editor.window
    editor_service.stop_server()
    assert wait_until(lambda: not editor.remote.online and win.offline_label.isVisible())
    assert win.offline_label.text() == ("Verbindung zum Dienst getrennt – Änderungen werden "
                                        "nachgereicht")
    assign(win, ControlRef("round", 1), "mute_toggle")  # Dienst weg: bleibt im Editor
    QTest.qWait(100)
    assert saved_round(editor_service, 1) is None
    assert editor.remote.pending_count() == 1
    editor_service.start_server()
    assert wait_until(lambda: saved_round(editor_service, 1) == {"type": "mute_toggle"})
    assert wait_until(lambda: editor.remote.online and not win.offline_label.isVisible())
    assert editor.remote.pending_count() == 0
    assign(win, ControlRef("round", 2), "mute_toggle")  # und danach geht es normal weiter
    assert wait_until(lambda: saved_round(editor_service, 2) == {"type": "mute_toggle"})


def test_put_in_flight_when_service_dies_is_resent(editor_service, editor):
    """Abgeschickt, aber der Dienst stirbt vor der Antwort: nach dem Neustart erneut."""
    win = editor.window
    assign(win, ControlRef("round", 5), "mute_toggle")  # geschrieben, noch nicht gelesen
    assert editor.remote.pending_count() == 1
    editor_service.stop_server()  # verwirft die ungelesene Anfrage
    assert wait_until(lambda: not editor.remote.online)
    assert saved_round(editor_service, 5) is None and editor.remote.pending_count() == 1
    editor_service.start_server()
    assert wait_until(lambda: saved_round(editor_service, 5) == {"type": "mute_toggle"})
    # Der Dienst speichert vor der Antwort: die Bestaetigung kommt erst danach im Editor an.
    assert wait_until(lambda: editor.remote.pending_count() == 0)


def test_close_with_unsent_changes_asks(editor_service, editor, monkeypatch):
    win = editor.window
    editor_service.stop_server()
    assert wait_until(lambda: not editor.remote.online)
    assign(win, ControlRef("round", 3), "mute_toggle")
    asked = []
    monkeypatch.setattr(editor_main, "DRAIN_S", 0.1)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No))
    win.close()
    assert asked and "1" in asked[0][2]
    assert win.isVisible()  # nicht geschlossen: Aenderung bleibt
    assert editor.remote.pending_count() == 1


def _big_profile_json() -> dict:
    p = Profile.empty()
    for page_no in range(20):
        page = TouchPage(f"x{page_no}", f"Seite {page_no}")
        page.buttons = [Assignment({"type": "run", "command": "echo " + "y" * 2000},
                                   ButtonImage(text=f"T{i}")) for i in range(12)]
        p.workspaces[0].touch_pages.append(page)
    return p.to_json()


_CRASH_CHILD = r"""
import os, signal, socket, sys
path, line_file, cut = sys.argv[1], sys.argv[2], int(sys.argv[3])
line = open(line_file, "rb").read()
s = socket.socket(socket.AF_UNIX)
s.connect(path)
s.sendall(line[:cut] if cut >= 0 else line)
os.kill(os.getpid(), signal.SIGKILL)
"""


def _crash_child(server: ApiServer, line: bytes, cut: int, tmp_path: Path) -> None:
    """Kindprozess schreibt (einen Teil von) ``line`` und stirbt hart (SIGKILL); kehrt erst
    zurueck, wenn der Dienst die Verbindung angenommen, gelesen und verworfen hat."""
    line_file = tmp_path / f"line-{uuid.uuid4().hex}.bin"
    line_file.write_bytes(line)
    before = server.transport.accepted
    proc = subprocess.Popen([sys.executable, "-c", _CRASH_CHILD,
                             server.transport.full_name, str(line_file), str(cut)])
    assert wait_until(lambda: proc.poll() is not None)
    assert proc.returncode == -9
    assert wait_until(lambda: server.transport.accepted > before and not server.connections)


def test_service_unaffected_by_editor_crash(editor_service, tmp_path):
    app = editor_service.app
    store = editor_service.store
    store.save(app.engine.profile)
    path = store.path("default")
    before = path.read_bytes()
    big = _big_profile_json()
    line = protocol.encode({"id": 1, "method": "profile.put", "params": {"profile": big}})
    assert len(line) > 200_000
    # mitten im Speichern-Auftrag abgestuerzt: nichts angekommen, alte Datei bleibt
    _crash_child(editor_service.server, line, len(line) // 2, tmp_path)
    assert path.read_bytes() == before
    assert len(app.engine.profile.workspaces[0].touch_pages) == 1
    # Auftrag ganz geschickt, dann abgestuerzt: neue Datei, ganz, mit Snapshot
    _crash_child(editor_service.server, line, -1, tmp_path)
    assert wait_until(lambda: path.read_bytes() != before)
    on_disk = Profile.from_json(json.loads(path.read_text(encoding="utf-8")))
    assert on_disk.to_json() == Profile.from_json(big).to_json()
    assert store.versions("default")
    # Dienst antwortet weiter, Geraet reagiert
    c = ApiClient(editor_service.name)
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    try:
        assert c.call_wait("ping") == "pong"
        assert c.call_wait("page", {"dir": "next"})["page"] == 1
    finally:
        c.close()
    n = len(app.device.draws)
    app.engine.redraw_all()
    assert len(app.device.draws) > n


def test_editor_starts_service():
    name = unique_name()
    holder = []

    def starter():  # „Dienst startet“: kommt erst nach 300 ms hoch
        QTimer.singleShot(300, lambda: holder.append(Service(name)))

    t0 = time.monotonic()
    ed = editor_main.start(server_name=name, starter=starter, timeout=15.0)
    try:
        assert time.monotonic() - t0 < 15.0  # sobald der Dienst da ist, nicht erst am Ende
        assert holder and ed.remote.online and ed.window.isVisible()
        assert ed.remote.profile.id == "default"
    finally:
        ed.shutdown()
        for s in holder:
            s.close()


def test_editor_reports_unreachable_service_instead_of_hanging():
    shown = []
    started = []
    t0 = time.monotonic()
    with pytest.raises(editor_main.ServiceUnavailable):
        editor_main.start(server_name=unique_name(), starter=lambda: started.append(1), timeout=0.5,
                          show_error=shown.append)
    # gibt nach dem eigenen Zeitlimit auf, nicht erst nach dem Standard (5 s) oder nie
    assert time.monotonic() - t0 < editor_main.EDITOR_CONNECT_TIMEOUT_S
    assert started == [1]
    assert shown and "Dienst" in shown[0]
    assert not [w for w in QApplication.topLevelWidgets()
                if isinstance(w, ConfigWindow) and w.isVisible()]


def test_second_editor_raises_first_and_exits(editor_service, editor):
    raised = []
    editor.remote.raise_requested.connect(lambda: raised.append(1))
    with pytest.raises(editor_main.AlreadyOpen):
        editor_main.start(server_name=editor_service.name, starter=no_start, timeout=2.0)
    assert wait_until(lambda: raised)
    assert editor_service.started_editors == []


# --- Dienst: Tray startet den Editor-Prozess ---------------------------------------------

def test_tray_opens_editor_process(editor_service):
    app = editor_service.app
    action = next(a for a in app.tray.menu.actions() if a.text() == "Einstellungen öffnen")
    action.trigger()
    # Starter mit dem Socket des Dienstes
    assert editor_service.started_editors == [editor_service.name]
    assert not [w for w in QApplication.topLevelWidgets()
                if isinstance(w, ConfigWindow) and w.isVisible()]
    app.engine.call("open_config", {})  # Taste am Geraet: ebenso
    assert editor_service.started_editors == [editor_service.name] * 2
    # laeuft schon ein Editor (angemeldet als „editor“): nach vorn holen statt neu starten
    c = ApiClient(editor_service.name)
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    try:
        events = []
        c.event.connect(lambda ev, data: events.append(ev))
        assert c.call_wait("subscribe", {"role": "editor"}) == {"editors": 0}
        action.trigger()
        assert wait_until(lambda: "raise" in events)
        assert len(editor_service.started_editors) == 2
    finally:
        c.close()


def test_service_does_not_import_config_window():
    code = ("import sys; import neondeck.service.app as m; "
            "print('neondeck.editor.windows.config_window' in sys.modules, hasattr(m, 'ConfigWindow'))")
    env = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False"]


def test_start_editor_command(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(api_client, "_spawn", lambda cmd, env: calls.append(cmd))
    monkeypatch.setattr(api_client, "launcher_path", lambda: tmp_path / "fehlt")
    api_client.start_editor("ldl-test-x")
    assert calls[0][0] == sys.executable
    assert calls[0][1:] == ["-m", "neondeck", "--config", "--server", "ldl-test-x"]
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    api_client.start_editor(protocol.socket_path())  # Standardadresse: ohne --server
    assert calls[1][1:] == ["-m", "neondeck", "--config"]
    launcher = tmp_path / "neondeck-ct"
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(0o755)
    monkeypatch.setattr(api_client, "launcher_path", lambda: launcher)
    api_client.start_editor(None)
    assert calls[2] == [str(launcher), "--config"]


def test_main_config_flag_runs_editor(monkeypatch):
    from neondeck import __main__ as entry
    got = []
    monkeypatch.setattr(editor_main, "run", lambda argv: got.append(argv) or 0)
    assert entry.run(["--config"]) == 0
    assert got == [["--config"]]


# --- Socket-Pfad (R19a) -------------------------------------------------------------------

def test_socket_path_in_runtime_dir(monkeypatch, tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    path = str(runtime / "neondeck-ct.sock")
    assert protocol.socket_path() == path
    assert ApiServer(poster=QtPoster()).name == path and ApiClient().name == path
    from neondeck import cli
    assert cli._parser().parse_args(["status"]).server is None  # -> ApiClient(None) -> Pfad
    server = ApiServer(OpenConfigFacade(), poster=QtPoster())
    assert server.listen()
    try:
        assert os.path.exists(path)
        from neondeck.service.instance import notify_running
        assert notify_running()  # Einzelinstanz ueber denselben Pfad
        c = ApiClient()
        assert c.connect_or_start(timeout=1.0, starter=no_start)
        assert c.call_wait("ping") == "pong"
        c.close()
    finally:
        server.close()
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert protocol.socket_path() == "neondeck-ct"


# --- Dienst raeumt importierte Symbole auf (R19b), Theme live (R19c) ---------------------

def test_profile_delete_via_api_removes_unused_imports(editor_service, tmp_path):
    store = editor_service.store
    first, _ = import_lp5(make_lp5(tmp_path / "a.lp5"), store)
    second, _ = import_lp5(make_lp5(tmp_path / "b.lp5"), store)
    orphan = paths.data_dir() / "imported" / "alt-123456"
    orphan.mkdir(parents=True)
    (orphan / "x.svg").write_text("<svg/>")
    copy = Profile.from_json(second.to_json())
    copy.id = "kopie"
    store.save(copy)
    c = ApiClient(editor_service.name)
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    try:
        c.call_wait("profile.delete", {"id": first.id})
        assert not imported_dir(first.id).exists()
        assert not orphan.exists()
        c.call_wait("profile.delete", {"id": second.id})
        assert imported_dir(second.id).is_dir()  # die Kopie nutzt die Symbole noch
    finally:
        c.close()


def test_settings_put_theme_applies_live_in_service(editor_service):
    c = ApiClient(editor_service.name)
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    try:
        c.call_wait("settings.put", {"theme": "neutral"})
        assert theme.current().name == "neutral"  # Tray-Menue des Dienstes sofort mit
        assert QApplication.instance().palette().window().color().name() == "#16181d"
        assert Settings.load().theme == "neutral"
    finally:
        c.close()


# --- Fix-Runde 1 ---------------------------------------------------------------------------

def test_overlapping_own_puts_keep_unsent_edit(editor_service, editor, monkeypatch):
    """Zwei eigene Speicher-Auftraege hintereinander sind keine fremde Aenderung: das Profil
    im Editor wird nicht ersetzt, die noch gebuendelte Aenderung bleibt und kommt an."""
    win, remote = editor.window, editor.remote
    # Der 300-ms-Puffer des Fensters darf unter Last nicht vor den Bestaetigungen ablaufen:
    # die Aenderung bleibt gebuendelt, bis der Test selbst speichert.
    monkeypatch.setattr(commit, "COMMIT_DELAY_MS", 3_600_000)
    editor_service.store.save(editor_service.app.engine.profile)
    assign(win, ControlRef("round", 0), "mute_toggle")  # Auftrag 1 unterwegs
    assign(win, ControlRef("round", 1), "mute_toggle")  # Auftrag 2 wartet dahinter
    assert len(remote.queue.pending_puts()) == 2
    win.select(ControlRef("round", 2))
    choose_type(win.editor.content.action_form, "mute_toggle")  # noch im Puffer des Fensters
    shown = win.engine.profile
    # beide Bestaetigungen sind da (profile.changed kommt je Profil vor der Antwort)
    assert wait_until(lambda: not remote.queue.pending_puts())
    assert win.commits.waiting()  # die dritte Aenderung ist noch nicht gesendet
    assert win.engine.profile is shown
    assert shown.round[protocol_round(2)].action == {"type": "mute_toggle"}
    assert saved_round(editor_service, 0) == saved_round(editor_service, 1) == \
        {"type": "mute_toggle"}
    win.flush()  # Puffer laeuft ab
    assert wait_until(lambda: saved_round(editor_service, 2) == {"type": "mute_toggle"})
    assert wait_until(lambda: not remote.queue.pending_puts())
    assert win.engine.profile.round[protocol_round(2)].action == {"type": "mute_toggle"}


def test_foreign_change_during_unsent_edit_editor_wins(editor_service, editor, monkeypatch):
    """Fremde Aenderung, waehrend das Fenster noch Ungespeichertes hat: der Editor ersetzt
    sein Profil nicht, sein Stand geht an den Dienst."""
    app, win, remote = editor_service.app, editor.window, editor.remote
    monkeypatch.setattr(commit, "COMMIT_DELAY_MS", 3_600_000)  # bleibt gebuendelt
    fetched = []
    real_got = remote.follower.got_active
    monkeypatch.setattr(remote.follower, "got_active",
                        lambda pid, r, e: (real_got(pid, r, e), fetched.append(pid)))
    editor_service.store.save(app.engine.profile)
    win.select(ControlRef("round", 6))
    choose_type(win.editor.content.action_form, "mute_toggle")  # gebuendelt, nicht gesendet
    shown = win.engine.profile
    d = app.engine.profile.to_json()
    d["name"] = "Fremd"
    app.engine.set_profile(Profile.from_json(d), keep_view=True)
    app.store.save(app.engine.profile)
    app.emit("profile.changed", {"id": "default", "active": "default"})
    assert wait_until(lambda: fetched == ["default"])  # fremden Stand geholt und abgewogen
    assert win.commits.waiting()  # die eigene Aenderung war dabei noch ungesendet
    assert win.engine.profile is shown
    win.flush()
    assert wait_until(lambda: saved_round(editor_service, 6) == {"type": "mute_toggle"})
    assert win.engine.profile is shown


def test_put_then_view_set_keep_order(editor_service, editor):
    app, win = editor_service.app, editor.window
    order = []
    for m in ("profile.put", "view.set"):
        real = editor_service.server.methods[m]
        editor_service.server.methods[m] = (lambda real, m: lambda c, p: order.append(m)
                                      or real(c, p))(real, m)
    win.pages.add_page()  # speichern (neue Seite), dann am Geraet zeigen
    assert wait_until(lambda: app.engine.page_index == 1)
    assert order[:2] == ["profile.put", "view.set"]
    assert len(app.engine.workspace.touch_pages) == 2
    assert "fehlgeschlagen" not in win.statusBar().currentMessage()


def test_rejected_put_stays_unsaved_close_asks_next_flush_retries(editor_service, editor,
                                                                monkeypatch):
    win, remote = editor.window, editor.remote
    real = editor_service.server.methods["profile.put"]

    def reject(conn, p):
        raise protocol.ApiError("profile.invalid", "Profil ungültig: Probe")

    editor_service.server.methods["profile.put"] = reject
    assign(win, ControlRef("round", 3), "mute_toggle")
    assert wait_until(lambda: "Speichern fehlgeschlagen: Profil ungültig: Probe"
                    in win.statusBar().currentMessage())
    assert remote.pending_count() == 1  # bleibt ungespeichert
    asked = []
    monkeypatch.setattr(editor_main, "DRAIN_S", 0.1)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No))
    win.close()
    assert asked and win.isVisible()
    editor_service.server.methods["profile.put"] = real
    assign(win, ControlRef("round", 4), "mute_toggle")  # naechstes Speichern versucht es neu
    assert wait_until(lambda: saved_round(editor_service, 4) == {"type": "mute_toggle"})
    assert saved_round(editor_service, 3) == {"type": "mute_toggle"}
    assert wait_until(lambda: remote.pending_count() == 0)


def test_switch_while_offline_has_own_message(editor_service, editor):
    win = editor.window
    editor_service.app.store.save(Profile.empty("zwei", "Zwei"))
    editor_service.stop_server()
    assert wait_until(lambda: not editor.remote.online)
    win.navigator.switch_to("zwei")
    msg = win.statusBar().currentMessage()
    assert msg == "Profilwechsel fehlgeschlagen: Nicht mit dem Dienst verbunden"
    assert protocol.SHOW_FAILED not in msg


def test_window_shown_before_profile_names_arrive(editor_service, monkeypatch):
    """Die Profilliste darf den Start nicht aufhalten: Fenster nach Ansicht + Profil."""
    from neondeck.editor.remote import engine as remote_engine
    # Wartete der Start auf die (zurueckgehaltene) Liste, hinge er bis zu dieser Grenze.
    monkeypatch.setattr(remote_engine, "READY_TIMEOUT_S", 60.0)
    real = editor_service.server.handle_line
    held = []

    def hold_list(conn, line):
        if b'"profile.list"' in line:
            held.append((conn, line))  # bleibt erst einmal unbeantwortet
            return
        real(conn, line)

    editor_service.server.handle_line = hold_list
    editor_service.app.store.save(Profile.empty("zwei", "Zwei"))
    t0 = time.monotonic()
    ed = editor_main.start(server_name=editor_service.name, starter=no_start, timeout=2.0)
    try:
        assert time.monotonic() - t0 < 15.0
        assert ed.window.isVisible() and ed.window.toolbar.profile_combo.findData("zwei") < 0
        editor_service.server.handle_line = real
        for conn, line in held:
            real(conn, line)  # Liste kommt nach: Fenster zieht nach
        assert wait_until(lambda: ed.window.toolbar.profile_combo.findData("zwei") >= 0)
    finally:
        ed.shutdown()


def test_legacy_listener_prevents_second_service(monkeypatch):
    from neondeck.service import app as app_main
    legacy = unique_name()
    monkeypatch.setattr(protocol, "LEGACY_NAME", legacy)
    facade = OpenConfigFacade()
    server = ApiServer(facade, legacy, poster=QtPoster())  # „alte Version“ unter der alten Adresse
    assert server.listen()
    try:
        assert app_main.main([]) == 0  # Standardadresse leer: findet die alte Instanz
        assert wait_until(lambda: facade.opened == 1)
        assert not os.path.exists(protocol.socket_path())  # kein zweiter Dienst
        c = ApiClient()
        assert c.connect_or_start(timeout=1.0, starter=no_start)  # Editor: nicht starten
        assert c.name == legacy and c.call_wait("ping") == "pong"
        c.close()
    finally:
        server.close()


def test_lock_refuses_second_service(capsys):
    from neondeck.service import app as app_main
    from neondeck.service.instance import acquire_instance_lock, notify_running
    fd = acquire_instance_lock()
    assert fd is not None
    try:
        name = unique_name()
        assert app_main.main([], server_name=name) == 1
        assert "Sperre" in capsys.readouterr().err
        assert not notify_running(name)  # es lauscht nichts Neues
        assert acquire_instance_lock() is None
    finally:
        os.close(fd)
    again = acquire_instance_lock()  # nach dem Ende wieder frei
    assert again is not None
    os.close(again)


def test_editor_with_server_starts_service_on_same_address(monkeypatch):
    from neondeck.service import app as app_main
    calls = []
    monkeypatch.setattr(api_client, "_spawn", lambda cmd, env: calls.append(cmd))
    name = unique_name()
    c = ApiClient(name)
    assert not c.connect_or_start(timeout=0.2)  # Standard-Starter, nichts kommt hoch
    assert calls and calls[0][-2:] == ["--server", name]
    assert app_main._parse(["--server", name]).server == name
    facade = OpenConfigFacade()
    server = ApiServer(facade, name, poster=QtPoster())
    assert server.listen()
    try:
        assert app_main.main(["--server", name]) == 0  # Dienst nimmt die Adresse an
        assert wait_until(lambda: facade.opened == 1)
    finally:
        server.close()


def test_editor_does_not_import_service_modules():
    code = ("import sys; import neondeck.editor.main; "
            "print(*(m in sys.modules for m in ('neondeck.service.app', "
            "'neondeck.device.ct', 'neondeck.api.server', "
            "'neondeck.engine.engine')))")
    env = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False", "False", "False"]


def test_editor_lists_apps_and_shortcuts_through_api(editor_service, editor):
    """P12: Auswahllisten (Anwendungen, KDE-Kürzel) kommen ueber die API vom Dienst; Kopieren/
    Einfuegen im Editor geht als profile.put an den Dienst."""
    editor_service.server.methods["apps.list"] = \
        lambda c, p: [{"id": "org.kde.kate", "name": "Kate"}]
    editor_service.server.methods["kde.shortcuts"] = lambda c, p: [
        {"component": "kwin", "name": "Overview", "friendly": "Übersicht"}]
    win = editor.window
    assert win.catalog.apps() == []  # Anfrage laeuft im Hintergrund
    assert wait_until(lambda: win.catalog.apps() == [{"id": "org.kde.kate", "name": "Kate"}])
    win.catalog.shortcuts()
    assert wait_until(lambda: len(win.catalog.shortcuts()) == 1)
    assign(win, ControlRef("round", 0), "mute_toggle")
    win.select(ControlRef("round", 0))
    win.edit.copy_selection()
    win.select(ControlRef("round", 2))
    win.edit.paste()
    win.flush()
    assert wait_until(lambda: saved_round(editor_service, 2) == {"type": "mute_toggle"})
