"""Menue „Ansicht“: Themes (live umgeschaltet) und Scanlines im Geraetebild. ``on_theme``
merkt die Wahl (Dienst: Einstellungen); angewandt wird sie hier."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu

from ...core.i18n import tr
from ...ui import theme
from ..widgets.base import menu_action


class ThemeMenu(QObject):
    def __init__(self, menu: QMenu, on_theme: Callable[[str, bool], None] | None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_theme = on_theme
        themes_menu = QMenu(tr("&Theme"), menu)
        menu.addMenu(themes_menu)
        self.theme_actions = QActionGroup(self)
        self.theme_actions.setExclusive(True)
        for t in theme.THEMES.values():
            a = QAction(tr(t.label), self.theme_actions)
            a.setData(t.name)
            a.setCheckable(True)
            a.triggered.connect(lambda _checked=False, name=t.name: self.set_theme(name))
            themes_menu.addAction(a)
        self.scanlines_action = menu_action(menu, None, tr("&Scanlines im Gerätebild"))
        self.scanlines_action.setCheckable(True)
        self.scanlines_action.triggered.connect(
            lambda checked: self.set_theme(theme.current().name, scanlines=checked))
        theme.notifier.changed.connect(self._show)
        self._show(theme.current())

    def set_theme(self, name: str, scanlines: bool | None = None) -> None:
        """Theme live wechseln (Scanlines bleiben, wenn nicht angegeben) und melden."""
        if scanlines is None:
            scanlines = self.scanlines_action.isChecked()
        t = theme.apply(QApplication.instance(), name, scanlines=scanlines)
        if self._on_theme is not None:
            self._on_theme(t.name, scanlines)

    def _show(self, current: theme.Theme) -> None:
        for a in self.theme_actions.actions():
            a.setChecked(a.data() == current.name)
        supported = current.supports_scanlines
        self.scanlines_action.setEnabled(supported)
        if supported:
            self.scanlines_action.setChecked(current.scanlines)
