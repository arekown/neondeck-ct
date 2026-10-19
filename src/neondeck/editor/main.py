"""Einstellungen als eigener Prozess: ``neondeck-ct --config``.

Der Editor hat kein Geraet, keine Engine und schreibt keine Profile selbst: Er verbindet
sich ueber die JSON-API mit dem Dienst (startet ihn notfalls) und zeigt das
``ConfigWindow`` mit einer ``RemoteEngine``. Stuerzt er ab, laeuft der Dienst weiter.
Schliessen des Fensters beendet den Editor-Prozess (vorher geht Ausstehendes raus).

Es gibt hoechstens einen Editor: Meldet der Dienst bei der Anmeldung schon einen, holt
der neue ihn ueber ``open_config`` nach vorn und beendet sich.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from ..api.client import EDITOR_CONNECT_TIMEOUT_S, ApiClient, ApiError
from ..core import i18n, logging_setup, paths
from ..core.errors import LoupedeckError
from ..core.i18n import N_, tr
from ..core.settings import autostart_entry
from ..ui import theme
from ..ui.common import APP_NAME, DESKTOP_NAME, DRAIN_S, apply_language, install_translations
from .remote.engine import RemoteEngine
from .widgets import shortcut_block
from .windows.config_window import ConfigWindow

log = logging.getLogger(__name__)

UNREACHABLE = N_("Der Neondeck-CT-Dienst ist nicht erreichbar und ließ sich nicht starten. "
                 "Bitte den Dienst starten (Anwendungsmenü oder „neondeck-ct“) und die "
                 "Einstellungen erneut öffnen.")
UNSENT_TITLE = N_("Einstellungen schließen")


class ServiceUnavailable(LoupedeckError):
    """Dienst nicht erreichbar (Meldung wurde gezeigt)."""


class AlreadyOpen(LoupedeckError):
    """Ein anderer Editor laeuft schon (er wurde nach vorn geholt)."""


def _show_error(text: str) -> None:
    QMessageBox.critical(None, tr("Neondeck CT – Einstellungen"), text)


class Editor(QObject):
    """Fenster + RemoteEngine eines Editor-Prozesses."""

    def __init__(self, remote: RemoteEngine, window: ConfigWindow) -> None:
        super().__init__()
        self.remote = remote
        self.window = window
        self._ask = True
        remote.failed.connect(window.say)
        remote.online_changed.connect(lambda online: window.set_offline(not online))
        remote.view_changed.connect(window.sync_from_engine)
        remote.profiles_changed.connect(window.reload_profiles)
        remote.raise_requested.connect(self.show_window)
        window.installEventFilter(self)

    def show_window(self) -> None:
        win = self.window
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()

    def first_run_if_needed(self) -> bool:
        """Ersteinrichtung zeigen, wenn der Dienst sie noch nicht als erledigt kennt (ein
        aelterer Dienst ohne die Einstellung: nie)."""
        settings = self.remote.settings_snapshot or {}
        if settings.get("first_run_done", True):
            return False
        QTimer.singleShot(0, self.window.extras.open_first_run)
        return True

    def eventFilter(self, obj, event) -> bool:
        if obj is self.window and event.type() == QEvent.Type.Close:
            if not self._may_close():
                event.ignore()
                return True
            QTimer.singleShot(0, self._closed)
        return False

    def _may_close(self) -> bool:
        """Ausstehendes speichern; was nicht ankommt, nur nach Rueckfrage verwerfen."""
        self.window.flush()
        if self.remote.drain(DRAIN_S) or not self._ask:
            return True
        n = self.remote.pending_count()
        answer = QMessageBox.question(
            self.window, tr(UNSENT_TITLE),
            tr("{count} geänderte(s) Profil(e) sind noch nicht im Dienst gespeichert (Dienst "
               "nicht erreichbar oder Speichern abgelehnt) und gehen beim Schließen "
               "verloren. Trotzdem schließen?", count=n))
        return answer == QMessageBox.StandardButton.Yes

    def _closed(self) -> None:
        if not self.window.isVisible():
            self.remote.close()
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def shutdown(self) -> None:
        """Ohne Rueckfrage schliessen (Signal, Tests)."""
        self._ask = False
        self.window.removeEventFilter(self)
        self.remote.blockSignals(True)  # nichts mehr an das Fenster, das gleich verschwindet
        self.window.flush()
        self.remote.drain(DRAIN_S if self.remote.online else 0)
        self.window.close()
        self.window.deleteLater()
        self.remote.close()


def start(*, server_name: str | None = None, starter: Callable[[], None] | None = None,
          timeout: float = EDITOR_CONNECT_TIMEOUT_S,
          show_error: Callable[[str], None] | None = None) -> Editor:
    """Editor aufbauen: Theme, Verbindung (Dienst notfalls starten), Fenster zeigen.

    ``ServiceUnavailable`` nach gezeigter Meldung, wenn der Dienst binnen ``timeout`` nicht
    erreichbar ist; ``AlreadyOpen``, wenn schon ein Editor laeuft (der kommt nach vorn).
    """
    qapp = QApplication.instance() or QApplication([sys.argv[0]])
    install_translations()
    shortcut_block.install()  # Kürzelsperre der Tastenaufnahme endet mit dem Prozess
    theme.load_fonts()
    theme.apply(qapp, theme.DEFAULT)  # auch eine Fehlermeldung schon im Stil
    remote = RemoteEngine(ApiClient(server_name))
    if not remote.start(timeout=timeout, starter=starter):
        remote.close()
        (show_error or _show_error)(tr(UNREACHABLE))
        raise ServiceUnavailable(tr(UNREACHABLE))
    if remote.other_editors:
        try:
            remote.request("open_config")
        except ApiError as e:
            log.warning("Laufender Editor nicht erreicht: %s", e)
        remote.close()
        raise AlreadyOpen()
    settings = remote.settings_snapshot or {}
    apply_language(str(settings.get("language") or i18n.AUTO))  # vor dem Fenster
    theme.apply(qapp, str(settings.get("theme") or theme.DEFAULT),
                scanlines=bool(settings.get("theme_scanlines", False)))
    window = ConfigWindow(remote.store, remote, remote.switch_profile, on_theme=remote.set_theme,
                          service=remote)
    editor = Editor(remote, window)
    editor.show_window()
    return editor


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="neondeck-ct --config",
                                description="Einstellungen von Neondeck CT")
    p.add_argument("--config", action="store_true", help="Einstellungen öffnen")
    p.add_argument("--server", default=None, help=argparse.SUPPRESS)  # Tests/zweiter Dienst
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    """Einstiegspunkt des Editor-Prozesses (eigene QApplication)."""
    args = _parse(argv)
    qapp = QApplication.instance() or QApplication([sys.argv[0]])
    qapp.setApplicationName(f"{APP_NAME} – Einstellungen")
    qapp.setDesktopFileName(DESKTOP_NAME)
    qapp.setQuitOnLastWindowClosed(False)  # beendet wird ueber Editor._closed
    notes = paths.migrate_legacy(autostart_entry())  # vor dem Log (liegt im Zustandsordner)
    logging_setup.setup(filename="editor-log.txt")
    for note in notes:
        log.info(note)
    try:
        editor = start(server_name=args.server)
    except ServiceUnavailable:
        return 1
    except AlreadyOpen:
        log.info("Einstellungen laufen schon – dort nach vorn geholt")
        return 0
    editor.first_run_if_needed()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: QTimer.singleShot(0, lambda: (editor.shutdown(),
                                                                    qapp.quit())))
    wake = QTimer()  # Python-Signalhandler laufen nur, wenn Python-Code an die Reihe kommt
    wake.timeout.connect(lambda: None)
    wake.start(500)
    log.info("Einstellungen gestartet")
    try:
        return qapp.exec()
    finally:
        wake.stop()
