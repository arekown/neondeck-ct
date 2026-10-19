"""Ergebnis eines Windows-Profil-Imports: was nicht uebernommen wurde."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QVBoxLayout

from ...core.i18n import tr
from ..widgets.base import close_buttons

REPORT_SIZE = (640, 420)


class ImportReport(QDialog):
    def __init__(self, name: str, messages: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Windows-Profil importiert"))
        self.resize(*REPORT_SIZE)
        if messages:
            text = tr("Das Profil „{name}“ wurde angelegt. Nicht umgesetzt oder übernommen "
                      "({count}):", name=name, count=len(messages))
        else:
            text = tr("Das Profil „{name}“ wurde vollständig übernommen.", name=name)
        label = QLabel(text)
        label.setWordWrap(True)
        self.list = QListWidget()
        self.list.addItems(messages)
        self.list.setVisible(bool(messages))
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.list, 1)
        layout.addWidget(close_buttons(self))
