"""Leiste ueber dem Geraetebild: Reiter der Touch-Seiten (ziehen = verschieben, Doppelklick =
umbenennen, Rechtsklick = Menue) und Knoepfe Hinzufügen/Entfernen/Umbenennen."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabBar, QWidget

from ...core.i18n import N_, tr
from ...profile.model import Workspace
from .base import tool_button

FOLDER_TIP = N_("Ordnerseite (öffnet sich über eine Ordner-Taste)")


class PageBar(QWidget):
    """``tabs`` meldet ``currentChanged``/``tabMoved``/``tabBarDoubleClicked`` und
    ``customContextMenuRequested``; die Knoepfe ``add_button``, ``remove_button``,
    ``rename_button`` verbindet das Fenster."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)  # Reiter ziehen = Seite verschieben
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.add_button = tool_button("list-add", "+", tr("Seite hinzufügen"), lambda: None)
        self.remove_button = tool_button("list-remove", "−", tr("Seite entfernen"), lambda: None)
        self.rename_button = tool_button("edit-rename", tr("Umbenennen"),
                                         tr("Seite umbenennen"), lambda: None)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("Touch-Seiten:")))
        row.addWidget(self.tabs, 1)
        for b in (self.add_button, self.remove_button, self.rename_button):
            row.addWidget(b)

    def current(self) -> int:
        return self.tabs.currentIndex()

    def select(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)

    def show_pages(self, ws: Workspace | None, index: int, page_shown: bool) -> None:
        """Reiter fuer die Seiten von ``ws`` (ohne Signale), Seite ``index`` gewaehlt."""
        with QSignalBlocker(self.tabs):
            while self.tabs.count():
                self.tabs.removeTab(0)
            for p in ws.touch_pages if ws else []:
                if p.folder:
                    i = self.tabs.addTab(QIcon.fromTheme("folder"), p.name or p.id)
                    self.tabs.setTabToolTip(i, tr(FOLDER_TIP))
                else:
                    self.tabs.addTab(p.name or p.id)
            self.tabs.setCurrentIndex(index)
        self.add_button.setEnabled(ws is not None)
        self.remove_button.setEnabled(bool(ws) and len(ws.touch_pages) > 1)
        self.rename_button.setEnabled(page_shown)
