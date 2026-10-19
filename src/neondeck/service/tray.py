"""Symbol im Systemabschnitt der Kontrollleiste mit Menue (Stil kommt vom App-Theme).

Ruhe: Meldungen haben eine Art (``error``, ``connection``, ``profile``), jede Art ist einzeln
abschaltbar (``set_notify``; abgeschaltete stehen nur im Log). Das Symbol gibt es farbig
oder einfarbig (``set_mono``: ``input-keyboard-symbolic`` aus dem Icon-Theme, sonst das
mitgelieferte einfarbige SVG).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from ..core.i18n import tr
from ..core.paths import bundled_dir

log = logging.getLogger(__name__)

TITLE = "Neondeck CT"
ICON_NAME = "input-keyboard"
MONO_ICON_NAME = "input-keyboard-symbolic"
NOTIFY_KINDS = ("error", "connection", "profile")
BRIGHTNESS_LEVELS = (2, 4, 6, 8, 10)
DISPLAY_SLEEP_CHOICES = (0, 5, 10, 30)  # Minuten, 0 = aus
MESSAGE_MS = 8000


@dataclass
class TrayState:
    """Anfangszustand des Menues."""
    brightness: int
    autostart: bool
    display_sleep: int = 0
    mono: bool = False
    notify: dict[str, bool] = field(default_factory=dict)  # Art -> Meldungen zeigen


@dataclass
class TrayActions:
    """Rueckrufe der Menueeintraege."""
    open_config: Callable[[], None]
    brightness: Callable[[int], None]
    autostart: Callable[[bool], None]
    quit: Callable[[], None]
    display_sleep: Callable[[int], None] = lambda _minutes: None


class Tray:
    def __init__(self, state: TrayState, on: TrayActions) -> None:
        self._notify = {kind: True for kind in NOTIFY_KINDS} | dict(state.notify)
        self.mono = state.mono
        self.icon = QSystemTrayIcon(self._make_icon(state.mono))
        self.menu = QMenu()

        self._status = QAction(self.menu)
        self._status.setEnabled(False)
        self.menu.addAction(self._status)
        self._add_action(tr("Einstellungen öffnen"), on.open_config)
        self._levels = self._add_choices(tr("Helligkeit"), {lv: str(lv) for lv in BRIGHTNESS_LEVELS},
                                         on.brightness)
        self.set_brightness(state.brightness)
        self._sleep = self._add_choices(
            tr("Display-Schlaf"),
            {m: tr("Aus") if m == 0 else tr("{n} min", n=m) for m in DISPLAY_SLEEP_CHOICES},
            on.display_sleep)
        self.set_display_sleep(state.display_sleep)

        self.autostart = QAction(tr("Mit Anmeldung starten"), self.menu)
        self.autostart.setCheckable(True)
        self.autostart.setChecked(state.autostart)
        self.autostart.triggered.connect(on.autostart)  # nur Benutzer-Klicks, nicht setChecked
        self.menu.addAction(self.autostart)
        self._add_action(tr("Beenden"), on.quit)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(
            lambda reason: on.open_config()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self._detail = ""
        self.set_status(tr("getrennt"))

    def _add_action(self, text: str, fn: Callable[[], None]) -> None:
        action = QAction(text, self.menu)
        action.triggered.connect(lambda _checked=False: fn())
        self.menu.addAction(action)

    def _add_choices(self, title: str, choices: dict[int, str],
                     fn: Callable[[int], None]) -> dict[int, QAction]:
        """Untermenue mit einer Auswahl (Haken), ``fn(wert)`` beim Klick."""
        sub = self.menu.addMenu(title)
        group = QActionGroup(sub)
        group.setExclusive(True)
        actions: dict[int, QAction] = {}
        for value, text in choices.items():
            a = QAction(text, sub)
            a.setCheckable(True)
            a.triggered.connect(lambda _checked=False, v=value: fn(v))
            group.addAction(a)
            sub.addAction(a)
            actions[value] = a
        return actions

    @staticmethod
    def _make_icon(mono: bool) -> QIcon:
        if mono:
            return QIcon.fromTheme(MONO_ICON_NAME, QIcon(str(
                bundled_dir() / "icons" / "neondeck-ct-mono.svg")))
        fallback = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        return QIcon.fromTheme(ICON_NAME, fallback)

    def set_mono(self, mono: bool) -> None:
        """Einfarbiges oder farbiges Symbol."""
        if mono != self.mono:
            self.mono = mono
            self.icon.setIcon(self._make_icon(mono))

    def set_notify(self, kind: str, enabled: bool) -> None:
        """Meldungen der Art ``kind`` zeigen oder nur ins Log schreiben."""
        self._notify[kind] = enabled

    def set_brightness(self, level: int) -> None:
        """Haken im Helligkeitsmenue setzen (Wert kam z. B. ueber die API)."""
        action = self._levels.get(level)
        if action is not None:
            action.setChecked(True)
        else:  # Zwischenwert: kein Eintrag passt
            for a in self._levels.values():
                a.setChecked(False)

    def set_display_sleep(self, minutes: int) -> None:
        """Haken im Menue „Display-Schlaf“ setzen (andere Werte, z. B. aus der API: keiner)."""
        for m, a in self._sleep.items():
            a.setChecked(m == minutes)

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def status_text(self) -> str:
        return self._status.text()

    def set_status(self, text: str) -> None:
        self._status.setText(text)
        self._update_tooltip()

    def set_detail(self, text: str) -> None:
        """Zweite Zeile im Tooltip, z. B. die letzte fehlgeschlagene Aktion."""
        self._detail = text
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        lines = [f"{TITLE} – {self._status.text()}"] + ([self._detail] if self._detail else [])
        self.icon.setToolTip("\n".join(lines))

    def notify(self, text: str, warning: bool = False, kind: str = "error") -> None:
        """Hinweis als Tray-Meldung (und im Log); abgeschaltete Arten nur im Log."""
        log.log(logging.WARNING if warning else logging.INFO, "Hinweis: %s", text)
        if not self._notify.get(kind, True):
            return
        kind = (QSystemTrayIcon.MessageIcon.Warning if warning
                else QSystemTrayIcon.MessageIcon.Information)
        self.icon.showMessage(TITLE, text, kind, MESSAGE_MS)
