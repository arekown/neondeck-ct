"""Was eine geaenderte Einstellung im Dienst bewirkt (Zuhoerer am ``SettingsController``).

Je Schluessel bzw. Gruppe eine Methode: sie liest die neuen Werte aus ``settings`` und gibt
sie an Geraet, Engine, Tray, Theme oder Autostart weiter. ``wire`` meldet alle an.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QApplication

from ..core.i18n import tr
from ..core.settings import FLAG_KEYS, Settings, set_autostart
from ..render import look, savers
from ..ui import theme
from .settings_controller import SettingRejected, SettingsController

if TYPE_CHECKING:
    from ..engine import Engine
    from ..engine.dynamic_mode import DynamicMode
    from .device_link import DeviceLink
    from .tray import Tray

log = logging.getLogger(__name__)

NOTIFY_SETTINGS = {"notify_errors": "error", "notify_connection": "connection",
                   "notify_profile": "profile"}
SAVER_KEYS = ("screensaver_min", "screensaver", "screensaver_folder", "screensaver_slide_s")


def saver_name(settings: Settings) -> str:
    return savers.resolve(settings.screensaver, settings.theme)


def saver_options(settings: Settings) -> dict:
    return {"folder": settings.screensaver_folder, "slide_s": settings.screensaver_slide_s}


def look_name(settings: Settings) -> str:
    return look.resolve(settings.device_look, settings.theme)


class SettingsEffects:
    """Die Zuhoerer; ``windows`` ist der KWin-Fensterwaechter (Dynamic Mode)."""

    def __init__(self, settings: Settings, *, engine: Engine, tray: Tray, link: DeviceLink,
                 dynamic: DynamicMode, windows: Any) -> None:
        self._s, self._engine, self._tray = settings, engine, tray
        self._link, self._dynamic, self._windows = link, dynamic, windows

    def wire(self, controller: SettingsController) -> None:
        listen = controller.listen
        listen(["brightness"], self.brightness)
        listen(["autostart"], self.autostart)
        listen(["dynamic_mode"], self.dynamic_mode)
        listen(["display_sleep_min"], self.display_sleep)
        listen(SAVER_KEYS, self.screensaver)
        listen(["lock_with_session"], self.lock_with_session)
        listen(["double_ms", "hold_ms"], self.key_timing)
        listen(FLAG_KEYS, self.flags)
        listen(["device_look"], self.device_look)
        listen(["theme", "theme_scanlines"], self.theme)

    def brightness(self) -> None:
        """Haken im Tray setzen und senden (gesperrt/im Display-Schlaf erst beim Wecken)."""
        self._tray.set_brightness(self._s.brightness)
        self._link.show_brightness()

    def autostart(self) -> None:
        enabled = self._s.autostart
        try:
            set_autostart(enabled)
        except OSError as e:
            log.error("Autostart nicht geaendert: %s", e)
            self._tray.autostart.setChecked(not enabled)
            self._tray.notify(tr("Autostart nicht geändert: {e}", e=e), warning=True)
            raise SettingRejected(str(e)) from e
        self._tray.autostart.setChecked(enabled)  # auch wenn der Wunsch ueber die API kam

    def dynamic_mode(self) -> None:
        """Beim Einschalten wird ein nicht laufender Fensterwaechter (z. B. KWin beim Start
        noch nicht bereit) neu gestartet."""
        enabled = self._s.dynamic_mode
        self._dynamic.enabled = enabled
        if enabled and not self._windows.running:
            log.info("Dynamic Mode eingeschaltet – KWin-Fensterwächter wird neu gestartet")
            if not self._windows.start():
                log.warning("KWin-Fensterwächter startet nicht – Dynamic Mode bleibt wirkungslos")

    def display_sleep(self) -> None:
        """Display-Schlaf nach so vielen Minuten (0 = aus: schlafende Displays sofort
        wecken); die Uhr laeuft ab jetzt neu."""
        self._engine.set_display_sleep(self._s.display_sleep_min)
        self._tray.set_display_sleep(self._s.display_sleep_min)

    def screensaver(self) -> None:
        """Wartezeit, Variante (``auto``: zum Theme), Diashow-Ordner und -Takt; die Uhr
        laeuft ab jetzt neu."""
        self._engine.set_saver(self._s.screensaver_min, saver_name(self._s),
                               saver_options(self._s))

    def lock_with_session(self) -> None:
        """Aus: ein gesperrtes Geraet wird frei."""
        if not self._s.lock_with_session:
            self._engine.unlock()

    def key_timing(self) -> None:
        """Schwellen fuer Doppeltippen/Halten, gelten ab dem naechsten Druecken."""
        self._engine.set_key_timing(self._s.double_ms, self._s.hold_ms)

    def flags(self) -> None:
        """Tray-Einstellungen gelten sofort (``first_run_done`` merkt der Dienst nur)."""
        self._tray.set_mono(self._s.tray_mono)
        for key, kind in NOTIFY_SETTINGS.items():
            self._tray.set_notify(kind, getattr(self._s, key))

    def device_look(self) -> None:
        self._engine.device_look = look_name(self._s)

    def theme(self) -> None:
        """Theme im Dienst sofort anwenden (Tray-Menue); der Editor wendet es bei sich an.
        ``auto`` bei Bildschirmschoner und Geraete-Look folgt dem Theme."""
        t = theme.apply(QApplication.instance(), self._s.theme, scanlines=self._s.theme_scanlines)
        self._s.theme = t.name
        self._engine.saver_name = saver_name(self._s)
        self._engine.device_look = look_name(self._s)
