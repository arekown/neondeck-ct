"""Tray-Anwendung (offscreen): Aufbau, Geraete-Anbindung, Einstellungen, Einzelinstanz."""
import json
import logging
import os
import shutil
import socket
import stat
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from PySide6.QtCore import QDir
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication

from neondeck.api.server import ApiServer
from neondeck.core import logging_setup, paths
from neondeck.core.settings import Settings, autostart_path
from neondeck.device.layout import Display
from neondeck.device.protocol import ButtonEvent
from neondeck.profile.store import ProfileStore
from neondeck.service import app as app_main
from neondeck.service.app import App
from neondeck.service.instance import notify_running
from neondeck.ui import common
from neondeck.ui.poster import QtPoster
from support.fakes import FakeDevice, FakeKeyboard
from support.service import OpenConfigFacade, unique_name
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("home")

DATA = Path(__file__).parent / "data"
SN = "CTTEST00000000000000000001"


@pytest.fixture
def qapp():
    app = QApplication.instance()
    assert isinstance(app, QApplication), "conftest muss eine QApplication anlegen"
    return app


def in_thread(fn, *args):
    t = threading.Thread(target=fn, args=args)
    t.start()
    t.join()


def texts(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


@pytest.fixture
def fake_app(qapp):
    kb = FakeKeyboard()
    app = App(device_factory=FakeDevice, keyboard=kb)
    yield app
    app.quit()


def test_tray_menu_and_clean_quit(qapp):
    kb = FakeKeyboard()
    app = App(port_finder=lambda: None, keyboard=kb)
    menu = app.tray.menu
    # P6: „Display-Schlaf“ (Aus/5/10/30 min) kam bewusst als sechster Eintrag dazu
    assert texts(menu) == ["getrennt", "Einstellungen öffnen", "Helligkeit", "Display-Schlaf",
                           "Mit Anmeldung starten", "Beenden"]
    sub = next(a for a in menu.actions() if a.text() == "Helligkeit").menu()
    assert texts(sub) == ["2", "4", "6", "8", "10"]
    assert [a.text() for a in sub.actions() if a.isChecked()] == ["8"]
    app.quit()
    app.quit()  # zweimal: harmlos
    assert kb.closed
    assert not [t for t in threading.enumerate() if t.name == "ct-device" and t.is_alive()]


def test_missing_assets_notice(qapp, caplog):
    with caplog.at_level(logging.INFO):
        app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert "Grafiken fehlen – tools/import_assets.py ausführen" in caplog.text
    finally:
        app.quit()


def test_device_callbacks_marshalled_to_gui_thread(fake_app):
    dev = fake_app.device
    seen = []
    fake_app.engine.handle = lambda ev: seen.append((ev, threading.current_thread()))
    in_thread(dev.on_state, True)
    in_thread(dev.on_event, ButtonEvent(7, True))
    assert not seen  # erst die Qt-Ereignisschleife fuehrt aus
    assert wait_until(lambda: seen)
    assert seen == [(ButtonEvent(7, True), threading.main_thread())]
    assert dev.brightness == [8]
    assert {d for d, _ in dev.draws} == set(Display)
    assert dev.leds
    assert fake_app.tray.status_text() == "verbunden"
    dev.serial = SN
    assert wait_until(lambda: fake_app.tray.status_text() == f"verbunden ({SN})")


def test_disconnect_resets_input_and_reconnect_redraws(fake_app):
    dev = fake_app.device
    resets = []
    real_reset = fake_app.engine.reset_input
    fake_app.engine.reset_input = lambda: (resets.append(1), real_reset())
    in_thread(dev.on_state, True)
    assert wait_until(lambda: dev.draws)
    in_thread(dev.on_state, False)
    assert wait_until(lambda: fake_app.tray.status_text() == "getrennt")
    assert resets == [1]
    dev.draws.clear()
    in_thread(dev.on_state, True)
    assert wait_until(lambda: {d for d, _ in dev.draws} == set(Display))
    assert dev.brightness == [8, 8]


def test_quit_blanks_displays_and_leds(qapp):
    kb = FakeKeyboard()
    app = App(device_factory=FakeDevice, keyboard=kb)
    dev = app.device
    assert dev.started
    app.quit()
    last = {d: data for d, data in dev.draws}
    assert set(last) == set(Display)
    for d, data in last.items():
        assert data == bytes(d.width * d.height * 2)
    assert dev.leds[-1] == {c: (0, 0, 0) for c in range(7, 15)}
    assert dev.stopped and kb.closed


def test_brightness_menu(fake_app):
    sub = next(a for a in fake_app.tray.menu.actions() if a.text() == "Helligkeit").menu()
    next(a for a in sub.actions() if a.text() == "4").trigger()
    assert fake_app.device.brightness[-1] == 4
    assert Settings.load().brightness == 4
    assert [a.text() for a in sub.actions() if a.isChecked()] == ["4"]


def test_autostart_toggle(fake_app):
    action = next(a for a in fake_app.tray.menu.actions() if a.text() == "Mit Anmeldung starten")
    assert action.isCheckable() and not action.isChecked()
    action.trigger()
    path = autostart_path()
    assert path.is_file()
    text = path.read_text()
    assert f"Exec={Path.home()}/.local/bin/neondeck-ct\n" in text
    assert "[Desktop Entry]" in text
    assert Settings.load().autostart is True
    action.trigger()
    assert not path.exists()
    assert Settings.load().autostart is False


def test_open_config_from_device_starts_editor_process(qapp):
    """Einstellungen laufen als eigener Prozess: der Dienst startet ihn nur (kein Fenster)."""
    started = []
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard(), editor_starter=started.append)
    try:
        app.engine.call("open_config", {})
        assert started == [None]  # ohne API-Server: Standardadresse
        assert not hasattr(app, "config_window")
    finally:
        app.quit()


def test_editor_start_failure_is_reported(qapp):
    def broken(name):
        raise FileNotFoundError("python fehlt")

    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard(), editor_starter=broken)
    notes = []
    app.tray.notify = lambda text, warning=False: notes.append(text)
    try:
        app.open_config()  # wirft nicht
        assert notes and "python fehlt" in notes[0]
    finally:
        app.quit()


def _install_template(home: Path) -> None:
    src = home / "share" / "assets" / "defaults" / "DefaultProfile20"
    src.mkdir(parents=True)
    shutil.copy(DATA / "synthetic-profile" / "ProfileInfo.json", src / "ProfileInfo.json")
    shutil.copytree(DATA / "synthetic-profile" / "ActionIcons", src / "ActionIcons")
    (home / "share" / "assets" / "manifest.json").write_text("{}")


def test_default_profile_created(qapp, home):
    _install_template(home)
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert app.engine.profile.name == "Standard (CT)"
        assert (home / "config" / "profiles" / "default.json").is_file()
    finally:
        app.quit()


def test_broken_default_backed_up_and_regenerated(qapp, home, caplog):
    _install_template(home)
    profiles = home / "config" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default.json").write_text("{kaputt")
    with caplog.at_level(logging.INFO):
        app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        backups = list(profiles.glob("default.json.kaputt-*"))
        assert len(backups) == 1 and backups[0].read_text() == "{kaputt"
        assert ProfileStore(profiles).load("default").name == "Standard (CT)"
        assert app.engine.profile.name == "Standard (CT)"
        assert "Standardprofil neu angelegt" in caplog.text
    finally:
        app.quit()


def test_broken_other_profile_falls_back_to_default(qapp, home, caplog):
    _install_template(home)
    Settings(active_profile="mein").save()
    profiles = home / "config" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "mein.json").write_text("[]")
    with caplog.at_level(logging.INFO):
        app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert app.engine.profile.id == "default"
        assert (profiles / "mein.json").read_text() == "[]"  # nicht ueberschrieben
        assert list(profiles.glob("mein.json.kaputt-*"))
        assert "Profil 'mein' ist kaputt" in caplog.text
    finally:
        app.quit()


def test_profile_switch_from_engine(fake_app, home):
    store = ProfileStore(home / "config" / "profiles")
    p = fake_app.engine.profile
    p.id, p.name = "zwei", "Zwei"
    store.save(p)
    fake_app.engine.call("profile", {"id": "zwei"})
    assert fake_app.engine.profile.name == "Zwei"
    assert Settings.load().active_profile == "zwei"
    fake_app.engine.call("profile", {"id": "gibtsnicht"})
    assert fake_app.engine.profile.name == "Zwei"


# --- Einstellungen, Logging ----------------------------------------------------------

def test_settings_controller_listeners_and_rejection():
    """Je Gruppe ein Aufruf, einmal speichern; ein abgelehnter Wert bleibt beim alten."""
    from neondeck.service.settings_controller import SettingRejected, SettingsController
    saves, seen = [], []
    ctl = SettingsController(Settings(), lambda: saves.append(1))
    ctl.listen(["double_ms", "hold_ms"], lambda: seen.append("timing"))

    def refuse():
        raise SettingRejected("nein")

    ctl.listen(["autostart"], refuse)
    ctl.listen(["theme"], lambda: 1 / 0)  # scheitert: die folgenden laufen trotzdem
    ctl.listen(["autostart", "theme", "hold_ms"], lambda: seen.append("danach"))
    ctl.apply({"double_ms": 200, "hold_ms": 800, "autostart": True, "theme": "classic"})
    assert seen == ["timing", "danach"] and saves == [1]
    assert (ctl.settings.double_ms, ctl.settings.autostart) == (200, False)
    with pytest.raises(KeyError):
        ctl.apply({"active_profile": "x"})  # nur ueber den Profilwechsel



def test_settings_defaults_roundtrip_and_broken(home):
    s = Settings.load()
    assert (s.active_profile, s.brightness, s.autostart) == ("default", 8, False)
    Settings(active_profile="x", brightness=4, autostart=True).save()
    data = json.loads((home / "config" / "settings.json").read_text())
    assert data == {"active_profile": "x", "brightness": 4, "autostart": True,
                    "theme": "cockpit", "theme_scanlines": False, "language": "auto",
                    "device_look": "auto",
                    "dynamic_mode": True, "display_sleep_min": 0,
                    "screensaver_min": 5, "screensaver": "auto",
                    "screensaver_folder": "", "screensaver_slide_s": 10,
                    "lock_with_session": True, "double_ms": 300, "hold_ms": 500,
                    "notify_errors": True, "notify_connection": True,
                    "notify_profile": False, "tray_mono": False, "first_run_done": False,
                    "last_pages": {}}
    assert Settings.load() == Settings("x", 4, True)
    (home / "config" / "settings.json").write_text("{kaputt")
    assert Settings.load() == Settings()
    (home / "config" / "settings.json").write_text(
        json.dumps({"active_profile": 3, "brightness": 99, "autostart": "ja"}))
    assert Settings.load() == Settings(brightness=10)


def test_logging_setup(home):
    root = logging.getLogger()
    old_level = root.level
    handlers = logging_setup.setup()
    try:
        files = [h for h in handlers if isinstance(h, RotatingFileHandler)]
        assert len(files) == 1
        fh = files[0]
        assert (fh.maxBytes, fh.backupCount) == (1_000_000, 3)
        assert Path(fh.baseFilename) == paths.state_dir() / "log.txt"
        assert root.level == logging.INFO
        logging.getLogger("neondeck.test").info("Hallo Protokoll")
        fh.flush()
        assert "Hallo Protokoll" in (home / "state" / "log.txt").read_text(encoding="utf-8")
        again = logging_setup.setup()  # kein doppeltes Anhaengen
        assert sum(isinstance(h, RotatingFileHandler) for h in root.handlers) == 1
        handlers = again
    finally:
        for h in handlers:
            root.removeHandler(h)
            h.close()
        root.setLevel(old_level)


# --- Einzelinstanz -------------------------------------------------------------------

def test_second_start_reaches_running_instance(qapp):
    name = unique_name()
    facade = OpenConfigFacade()
    server = ApiServer(facade, name, poster=QtPoster())
    assert server.listen()
    try:
        assert notify_running(name)
        assert wait_until(lambda: facade.opened)
    finally:
        server.close()
    assert not notify_running(name)


def test_plain_connection_does_not_open_config(qapp):
    """Nur die Anfrage ``open_config`` oeffnet das Fenster – nicht jede Verbindung (CLI)."""
    name = unique_name()
    facade = OpenConfigFacade()
    server = ApiServer(facade, name, poster=QtPoster())
    assert server.listen()
    try:
        sock = QLocalSocket()
        sock.connectToServer(name)
        assert sock.waitForConnected(15000)
        sock.disconnectFromServer()
        # erst pruefen, wenn der Dienst die Verbindung angenommen und wieder verworfen hat
        assert wait_until(lambda: server.transport.accepted and not server.connections)
        assert facade.opened == 0
    finally:
        server.close()


def test_stale_socket_removed(qapp):
    name = unique_name()
    path = os.path.join(QDir.tempPath(), name)
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(path)  # Datei bleibt liegen, niemand hoert zu
    stale.close()
    assert not notify_running(name)
    server = ApiServer(OpenConfigFacade(), name, poster=QtPoster())
    try:
        assert server.listen()
        assert notify_running(name)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600  # nur der eigene Benutzer
    finally:
        server.close()


def test_main_with_running_instance_exits(qapp):
    name = unique_name()
    facade = OpenConfigFacade()
    server = ApiServer(facade, name, poster=QtPoster())
    assert server.listen()
    try:
        assert app_main.main([], server_name=name) == 0
        assert wait_until(lambda: facade.opened == 1)
    finally:
        server.close()


def test_app_installs_qt_translations(qapp):
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not QTranslator().load(QLocale.system(), "qtbase", "_", folder):
        pytest.skip("keine Qt-Uebersetzung fuer die Systemsprache")
    common.remove_translations()
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert common._translators  # App hat die Qt-Uebersetzungen geladen (Systemsprache)
    finally:
        app.quit()


def test_qt_translation_german_buttons(qapp):
    from PySide6.QtCore import QLibraryInfo, QLocale
    from PySide6.QtWidgets import QDialogButtonBox
    folder = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if not (folder / "qtbase_de.qm").is_file():
        pytest.skip("qtbase_de.qm fehlt")
    try:
        assert common.install_translations(QLocale(QLocale.Language.German,
                                                     QLocale.Country.Germany))
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        assert box.button(QDialogButtonBox.StandardButton.Cancel).text() != "Cancel"
    finally:
        common.remove_translations()


# --- Themes -------------------------------------------------------------------------

def test_app_applies_theme_from_settings(qapp):
    from neondeck.ui import theme
    Settings(theme="neutral").save()
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert theme.current().name == "neutral"
        assert qapp.palette().window().color().name() == "#16181d"
        assert "Rajdhani" in theme.load_fonts()  # Schriften fuer Dienst und Editor geladen
    finally:
        app.quit()


def test_app_default_theme_is_cockpit(fake_app, qapp):
    from neondeck.ui import theme
    assert theme.current().name == "cockpit"
    assert qapp.styleSheet()  # Tray-Menue liegt in derselben QApplication: mitgestylt


# --- Zustandsquellen -----------------------------------------------------------------

def test_state_sources_wired_to_engine(qapp, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    class FakeSource(QObject):
        changed = Signal(object, object)
        started = stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    class FakeMedia(FakeSource):
        changed = Signal(bool)

    audio, media = FakeSource(), FakeMedia()
    monkeypatch.setattr(app_main, "_make_audio_state", lambda: audio)
    monkeypatch.setattr(app_main, "_make_mpris", lambda: media)
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    states = app.engine.states
    try:
        assert audio.started and media.started
        audio.changed.emit("mic_mute", True)
        media.changed.emit(True)
        assert states.flag("mic_mute") is True and states.flag("media") is True
        app.windows.handle_windows('[{"resourceClass": "firefox", "desktopFileName": "", '
                                '"caption": "x", "pid": 3, "internalId": "{1}"}]')
        assert [w.resource_class for w in states._windows] == ["firefox"]
    finally:
        app.quit()
    assert audio.stopped and media.stopped


def test_default_audio_and_mpris_are_fakes_in_tests(qapp):
    """conftest: der Dienst startet in Tests nie echtes pactl und fragt keinen echten Bus."""
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    try:
        assert all(type(p).__name__ == "FakeProcess" for p in app.audio._reads.values())
        assert app.audio._sub is not None and type(app.audio._sub).__name__ == "FakeProcess"
    finally:
        app.quit()
