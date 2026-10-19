"""Tray-Anwendung (Dienst): Kompositionswurzel fuer Einstellungen, Profile, Engine, Geraet,
Fensterwaechter, Zustandsquellen, API und Tray.

Die Engine laeuft im Qt-GUI-Thread. Alles aus anderen Threads (Geraete-Thread,
Aktions-Threads) kommt ueber ``QtPoster.post`` (``ui.poster``) nicht blockierend dorthin.
Die Teile: ``DeviceLink`` (Verbindung, Meldungen, Standby), ``ProfileSwitcher``,
``AnimationTimers``, ``SettingsController`` mit ``SettingsEffects``, ``instance``
(Einzelinstanz).

Das Einstellungsfenster laeuft als eigener Prozess (``--config``, ``editor_main``) und
spricht nur ueber die JSON-API mit dem Dienst; „Einstellungen öffnen“ startet ihn
losgeloest oder holt einen laufenden nach vorn.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from ..actions.base import ActionContext, Executor
from ..actions.keyboard import Keyboard
from ..actions.mouse import Mouse
from ..api import client as api_client
from ..api import protocol
from ..api.server import ApiServer
from ..core import logging_setup, paths
from ..core.assets import assets_dir
from ..core.guard import call_logged
from ..core.i18n import N_, tr
from ..core.settings import Settings, autostart_enabled, autostart_entry
from ..core.windows import WindowInfo
from ..desktop.audio_state import AudioState
from ..desktop.kwin import KWinWatcher
from ..desktop.mpris import Mpris
from ..desktop.session import SessionWatcher
from ..device.ct import CTDevice
from ..device.discovery import find_ct
from ..engine import Engine
from ..engine.dynamic_mode import DEFAULT_IGNORE, DynamicMode
from ..engine.ports import EngineHooks, EngineOptions, EnginePorts
from ..profile.model import Profile
from ..profile.store import ProfileStore
from ..render import savers
from ..ui import theme
from ..ui.common import APP_NAME, DESKTOP_NAME, apply_language, install_translations
from ..ui.poster import QtPoster
from .animation import AnimationTimers
from .device_link import DeviceLink
from .instance import acquire_instance_lock, lock_path, notify_running
from .profiles import ProfileSwitcher
from .settings_controller import SettingsController
from .settings_effects import NOTIFY_SETTINGS, SettingsEffects, look_name, saver_name, saver_options
from .tray import Tray, TrayActions, TrayState

log = logging.getLogger(__name__)

TICK_MS = 1000
ALREADY_RUNNING = N_("Neondeck CT läuft bereits – Einstellungen werden dort geöffnet.")
LOCKED = N_("Neondeck CT läuft bereits (Sperre {path} ist belegt), antwortet aber nicht – "
           "kein zweiter Start. Bitte die laufende Instanz beenden und neu starten.")
ASSETS_MISSING = N_("Grafiken fehlen – tools/import_assets.py ausführen")


def _make_window_watcher() -> KWinWatcher:
    """Fensterwaechter am echten KWin (Tests ersetzen diese Funktion)."""
    return KWinWatcher()


def _make_session_watcher() -> SessionWatcher:
    """Standby/Sperre an den echten Bussen (Tests ersetzen diese Funktion)."""
    return SessionWatcher()


def _make_audio_state() -> AudioState:
    """Stumm-Zustand ueber echtes ``pactl subscribe`` (Tests ersetzen diese Funktion)."""
    return AudioState()


def _make_mpris() -> Mpris:
    """Medien-Zustand am echten Session-Bus (Tests ersetzen diese Funktion)."""
    return Mpris()


class App:
    """Die laufende Anwendung (ohne QApplication; die legt ``main`` an); erfuellt
    ``api.contracts.ServiceFacade`` fuer den ``ApiServer``.

    Reihenfolge: Einstellungen, Tray, Profil, Eingabe, Geraet, Waechter; dann die Engine
    (sie braucht Geraet, Waechter und Timer); zuletzt wird alles gestartet und verbunden.
    Fensterwaechter und Zustandsquellen kommen aus den ``_make_*``-Funktionen (Tests
    ersetzen sie)."""

    def __init__(self, *, port_finder: Callable[[], str | None] = find_ct,
                 device_factory: Callable[..., CTDevice] = CTDevice,
                 keyboard: Keyboard | None = None, mouse: Mouse | None = None,
                 editor_starter: Callable[[str | None], None] | None = None):
        self._closed = False
        self._poster = QtPoster()
        self._listeners: list[Callable[[str, dict], None]] = []
        self._editor_starter = editor_starter  # Standard: api.client.start_editor
        self.api: ApiServer | None = None  # setzt ApiServer.attach
        self.settings = Settings.load()
        apply_language(self.settings.language)  # vor dem ersten Fenster und Text
        self.settings_controller = SettingsController(self.settings, self._save_settings)
        self.tray = self._make_tray()
        self.store = ProfileStore(paths.config_dir() / "profiles")
        self.profiles = ProfileSwitcher(self.store, self.settings, self.tray,
                                        save=self._save_settings, emit=self.emit)
        profile = self.profiles.startup()
        self.keyboard = keyboard if keyboard is not None else Keyboard()
        self.mouse = mouse if mouse is not None else Mouse()  # uinput erst beim ersten Scrollen
        self.device = device_factory(
            port_finder=port_finder,
            on_event=lambda ev: self._poster.post(partial(self._handle_event, ev)),
            on_state=lambda up: self._poster.post(partial(self.device_link.on_state, up)))
        self.device_link = DeviceLink(self.device, self.tray, self.settings, emit=self.emit,
                                      call_later=self.call_later)
        self.windows = _make_window_watcher()
        self.audio = _make_audio_state()
        self.mpris = _make_mpris()
        self.session = _make_session_watcher()
        self.animation = AnimationTimers(self._poster)
        self.engine = self._make_engine(profile)
        self.dynamic = self._make_dynamic_mode()
        self.device_link.attach(self.engine)
        self.animation.attach(self.engine)
        self.profiles.attach(self.engine, self.dynamic)
        SettingsEffects(self.settings, engine=self.engine, tray=self.tray, link=self.device_link,
                        dynamic=self.dynamic, windows=self.windows).wire(self.settings_controller)
        self._start()

    # --- Aufbau ------------------------------------------------------------------------

    def _make_tray(self) -> Tray:
        s = self.settings
        theme.load_fonts()
        theme.apply(QApplication.instance(), s.theme,
                    scanlines=s.theme_scanlines)  # vor dem Tray: Menue mitgestylt
        autostart = autostart_enabled()
        if autostart != s.autostart:
            s.autostart = autostart  # die Datei zaehlt
        apply = self.settings_controller.apply
        tray = Tray(TrayState(brightness=s.brightness, autostart=autostart,
                              display_sleep=s.display_sleep_min, mono=s.tray_mono,
                              notify={kind: getattr(s, key)
                                      for key, kind in NOTIFY_SETTINGS.items()}),
                    TrayActions(open_config=self.open_config,
                                brightness=lambda level: apply({"brightness": level}),
                                autostart=lambda on: apply({"autostart": on}), quit=self.quit,
                                display_sleep=lambda m: apply({"display_sleep_min": m})))
        tray.show()
        if not (assets_dir() / "manifest.json").is_file():
            tray.notify(tr(ASSETS_MISSING), warning=True)
        return tray

    def _make_engine(self, profile: Profile) -> Engine:
        s, link, gui = self.settings, self.device_link, self.animation
        return Engine(
            profile,
            EnginePorts(self.device.draw, self.device.set_leds, self._make_executor,
                        post=self._poster.post, call_later=self.call_later),
            hooks=EngineHooks(
                on_open_config=self.open_config, on_status=self.tray.set_detail,
                on_profile=self.switch_profile,
                on_view=lambda: self.emit("view.changed", self.engine.view_state()),
                on_value=lambda ref, text: self.emit("value", {"ref": protocol.format_ref(ref),
                                                               "text": text}),
                on_dark=link.on_dark, on_saver=gui.on_saver, on_animate=gui.on_animate),
            options=EngineOptions(
                views=s.last_pages, display_sleep_min=s.display_sleep_min,
                double_ms=s.double_ms, hold_ms=s.hold_ms, saver_min=s.screensaver_min,
                saver_name=saver_name(s), saver_options=saver_options(s),
                device_look=look_name(s)))

    def _make_dynamic_mode(self) -> DynamicMode:
        """Dynamic Mode: Profil folgt dem aktiven Fenster (KWin-Skript, ereignisgesteuert)."""
        dynamic = DynamicMode(self.store, partial(self.switch_profile, auto=True),
                              time.monotonic, call_later=self.call_later,
                              current=lambda: self.engine.profile.id,
                              ignore=(*DEFAULT_IGNORE, DESKTOP_NAME))
        dynamic.enabled = self.settings.dynamic_mode
        return dynamic

    def _mpris_call(self, method: str) -> Callable[..., None]:
        """MPRIS-Methode aus einem Aktions-Thread im GUI-Thread aufrufen (MPRIS laeuft dort)."""
        return lambda *args: self._poster.post(partial(getattr(self.mpris, method), *args))

    def _make_executor(self, engine_call, on_result) -> Executor:
        return Executor(ActionContext(engine_call=engine_call, keyboard=self.keyboard,
                                      focus=self.windows.focus, mouse=self.mouse,
                                      place=self.windows.expect_window,
                                      media_loop=self._mpris_call("cycle_loop"),
                                      media_control=self._mpris_call("control")),
                        on_result)

    def _start(self) -> None:
        """Takt, Geraet, Fensterwaechter, Zustandsquellen und Sitzungswaechter starten."""
        run, engine, link = self._poster.run, self.engine, self.device_link
        self._timer = QTimer()
        self._timer.timeout.connect(partial(run, engine.tick))
        self._timer.start(TICK_MS)
        self.device.start()
        self.windows.activated.connect(self._on_window)
        self.windows.windows_changed.connect(lambda ws: run(partial(engine.set_windows, ws)))
        self.windows.start()
        engine.set_windows(self.windows.windows)
        # Zustandsquellen: stumm (pactl), Medien (MPRIS); App laeuft kommt oben aus KWin
        self.audio.changed.connect(lambda kind, value: run(
            partial(engine.set_source_value, kind, value)))
        self.audio.start()
        self.mpris.changed.connect(lambda playing: run(
            partial(engine.set_source_value, "media", playing)))
        self.mpris.start()
        # Standby und Bildschirmsperre (logind / Bildschirmschoner)
        self.session.about_to_sleep.connect(partial(run, link.on_about_to_sleep))
        self.session.resumed.connect(partial(run, link.on_resumed))
        self.session.locked.connect(lambda locked: run(partial(self._on_locked, locked)))
        self.session.start()

    # --- Fassade fuer die API ----------------------------------------------------------

    def add_listener(self, fn: Callable[[str, dict], None]) -> None:
        """``fn(name, data)`` bei Ansichts-, Geraete-, Wert- und Profilwechseln."""
        self._listeners.append(fn)

    def emit(self, name: str, data: dict) -> None:
        for fn in list(self._listeners):  # ein Zuhoerer darf die App nicht stoeren
            call_logged(fn, name, data, what="Ereignis %s nicht zugestellt", what_args=(name,),
                        logger=log)

    def device_status(self) -> dict:
        return self.device_link.status()

    def diag_info(self) -> dict:
        """Was nur der Dienst weiss, fuer die Diagnose (API ``diag``); fragt beim
        verbundenen Geraet die Firmware-Version an, solange sie unbekannt ist."""
        return {**self.device_status(), "firmware": self.device_link.firmware(),
                "kwin_script": self.windows.running,
                "dbus_service": getattr(self.windows, "registered", False),
                "session_watcher": list(getattr(self.session, "active_signals", [])),
                "dynamic_mode": self.settings.dynamic_mode}

    @property
    def dynamic_mode(self) -> bool:
        """Profilwechsel nach aktivem Fenster: eingeschaltet und KWin-Skript aktiv."""
        return self.settings.dynamic_mode and self.windows.running

    def switch_profile(self, pid, *, auto: bool = False) -> None:
        """Profilwechsel (``ProfileSwitcher.switch``)."""
        self.profiles.switch(pid, auto=auto)

    def start_screensaver(self, name: str | None = None) -> bool:
        """Vorschau: sofort starten (``name``: Variante, sonst die eingestellte)."""
        return self.engine.start_saver(savers.resolve(name, self.settings.theme)
                                       if name else None)

    def open_config(self) -> None:
        """Einstellungen zeigen: ein laufender Editor (an der API als „editor“ angemeldet)
        kommt nach vorn, sonst wird der Editor-Prozess losgeloest gestartet."""
        if self._closed:
            return
        if self.api is not None and self.api.raise_editor():
            return
        starter = self._editor_starter or api_client.start_editor
        try:
            starter(self.api.name if self.api is not None else None)
        except OSError as e:
            log.error("Editor nicht gestartet: %s", e)
            self.tray.notify(tr("Einstellungen nicht geöffnet: {e}", e=e), warning=True)

    # --- Ereignisse --------------------------------------------------------------------

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> None:
        QTimer.singleShot(max(0, round(delay_s * 1000)), self._poster,
                          partial(self._poster.run, fn))

    def _handle_event(self, ev) -> None:
        self.engine.handle(ev)

    def _on_window(self, info: WindowInfo) -> None:
        self.emit("window.active", {"resource_class": info.resource_class,
                                    "desktop_file": info.desktop_file,
                                    "caption": info.caption, "pid": info.pid})
        self.dynamic.on_window(info)

    def _on_locked(self, locked: bool) -> None:
        if locked and self.settings.lock_with_session:
            self.engine.lock()
        elif not locked:
            self.engine.unlock()

    def _save_settings(self) -> None:
        self.settings.last_pages = self.engine.remembered_views(self.store.list())
        try:
            self.settings.save()
        except OSError as e:
            log.error("Einstellungen nicht gespeichert: %s", e)

    def quit(self) -> None:
        """Aktionen beenden, Displays schwarz, LEDs aus, Geraet schliessen (einmalig)."""
        if self._closed:
            return
        self._closed = True
        self.device_link.close()
        self._timer.stop()
        self.animation.stop()
        self._poster.enabled = False
        for step in (self.session.stop, self.windows.stop, self.audio.stop, self.mpris.stop,
                     self._save_settings,
                     self.engine.shutdown, self.device_link.blank, self.device.stop,
                     self.keyboard.close, self.mouse.close, self.tray.hide):
            try:
                step()
            except Exception:
                log.exception("Beenden: %s fehlgeschlagen", getattr(step, "__name__", step))
        log.info("Neondeck CT beendet")
        QCoreApplication.quit()


# --- Start ------------------------------------------------------------------------------

def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="neondeck-ct", description="Loupedeck CT unter Linux "
                                "(Einstellungen: neondeck-ct --config)")
    p.add_argument("--server", default=None, help=argparse.SUPPRESS)  # Tests/zweite Adresse
    return p.parse_args(argv)


def _handle_signals(app: App) -> QTimer:
    """SIGINT/SIGTERM beenden sauber (Displays schwarz)."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: QTimer.singleShot(0, app.quit))
    wake = QTimer()  # Python-Signalhandler laufen nur, wenn Python-Code an die Reihe kommt
    wake.timeout.connect(lambda: None)
    wake.start(500)
    return wake


def main(argv: list[str] | None = None, *, server_name: str | None = None) -> int:
    """Dienst starten (Tray, Geraet, API). Laeuft schon einer, oeffnet der die Einstellungen;
    es laufen nie zwei Dienste (Socket und Sperrdatei)."""
    args = _parse(argv)
    server_name = server_name or args.server
    qapp = QApplication.instance() or QApplication([sys.argv[0]])
    qapp.setApplicationName(APP_NAME)
    qapp.setDesktopFileName(DESKTOP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    install_translations()
    if notify_running(server_name):
        print(tr(ALREADY_RUNNING), file=sys.stderr)
        return 0
    notes = paths.migrate_legacy(autostart_entry())  # vor der Sperre (liegt im Zustandsordner)
    lock = acquire_instance_lock()
    if lock is None:
        print(tr(LOCKED, path=lock_path()), file=sys.stderr)
        return 1
    try:
        return _serve(qapp, server_name or protocol.socket_path(), notes)
    finally:
        os.close(lock)


def _serve(qapp: QApplication, server_name: str, notes: list[str]) -> int:
    logging_setup.setup()
    for note in notes:
        log.info(note)
    server = ApiServer(name=server_name, poster=QtPoster())  # vor dem Geraet: der Socket ist die Sperre
    if not server.listen() and notify_running(server_name):  # gleichzeitig gestartet
        print(tr(ALREADY_RUNNING), file=sys.stderr)
        return 0
    app = App()
    server.attach(app)
    qapp.aboutToQuit.connect(app.quit)
    wake = _handle_signals(app)
    log.info("Neondeck CT gestartet")
    try:
        return qapp.exec()
    finally:
        wake.stop()
        app.quit()
        server.close()
