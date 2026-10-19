"""Dialog „Versionen“: Snapshots eines Profils ansehen und eines wiederherstellen.

Liste aus ``versions.list`` (neueste zuerst), Vorschau als Geraeteansicht des Snapshots
(``versions.get``, nur lesend), „Wiederherstellen“ ueber ``versions.restore`` – der Dienst
sichert vorher den aktuellen Stand als eigene Version, ein Irrtum laesst sich also wieder
zuruecknehmen.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import tr
from ...profile.model import Profile
from ...ui.common import Request
from ..widgets.device_view import DeviceView

log = logging.getLogger(__name__)



def version_label(entry: dict) -> str:
    t = entry.get("time")
    when = datetime.fromtimestamp(t).strftime("%d.%m.%Y %H:%M:%S") if t else entry["name"]
    size = entry.get("size") or 0
    return tr("{when}  ({kb} KB)", when=when, kb=max(1, round(size / 1024)))


class VersionsDialog(QDialog):
    restored = Signal(str)  # Profil-ID

    def __init__(self, request: Request, profile_id: str, profile_name: str = "",
                 parent=None, *, before_restore: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self._request = request
        self.profile_id = profile_id
        self._before_restore = before_restore
        self._names: list[str] = []   # Snapshot-Namen in Listenreihenfolge
        self.preview_profile: Profile | None = None
        self.setWindowTitle(tr("Versionen – {name}", name=profile_name or profile_id))
        self.resize(1100, 640)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_version)
        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self._show_page)
        self.preview = DeviceView()
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.preview.setAcceptDrops(False)
        self.note = QLabel()
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.restore_button = QPushButton(tr("Wiederherstellen"))
        self.restore_button.clicked.connect(self.restore)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Seite:")))
        row.addWidget(self.page_combo, 1)
        right_layout.addLayout(row)
        right_layout.addWidget(self.preview, 1)
        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 800])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.restore_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Vor jedem Speichern wird der alte Stand gesichert (bis zu 100 "
                                   "Versionen, 60 Tage). Wiederherstellen sichert vorher den "
                                   "aktuellen Stand.")))
        layout.addWidget(split, 1)
        layout.addWidget(self.note)
        layout.addWidget(buttons)
        self.reload()

    # --- Liste und Vorschau ------------------------------------------------------------

    def reload(self) -> None:
        try:
            versions = self._request("versions.list", {"id": self.profile_id})
        except Exception as e:  # noqa: BLE001 - Dienst weg
            versions = []
            self.note.setText(tr("Versionen nicht geladen: {error}", error=e))
        versions = [v for v in versions or [] if isinstance(v, dict) and v.get("name")]
        self._names = [v["name"] for v in versions]
        self.list.clear()
        self.list.addItems([version_label(v) for v in versions])
        if not versions:
            self.note.setText(self.note.text() or tr("Für dieses Profil gibt es noch keine "
                                                     "Versionen."))
            self._show_version(-1)
        else:
            self.list.setCurrentRow(0)

    def selected_name(self) -> str | None:
        row = self.list.currentRow()
        return self._names[row] if 0 <= row < len(self._names) else None

    def _show_version(self, row: int) -> None:
        self.preview_profile = None
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        self.page_combo.blockSignals(False)
        name = self._names[row] if 0 <= row < len(self._names) else None
        self.restore_button.setEnabled(name is not None)
        if name is None:
            self.preview.set_view(None, None, None)
            return
        try:
            data = self._request("versions.get", {"id": self.profile_id, "name": name})
            self.preview_profile = Profile.from_json(data)
        except Exception as e:  # noqa: BLE001 - kaputter Snapshot: keine Vorschau
            log.warning("Version %s nicht lesbar: %s", name, e)
            self.note.setText(tr("Vorschau nicht möglich: {error}", error=e))
            self.preview.set_view(None, None, None)
            return
        self.page_combo.blockSignals(True)
        for wi, ws in enumerate(self.preview_profile.workspaces):
            for pi, page in enumerate(ws.touch_pages):
                self.page_combo.addItem(f"{ws.name or ws.id} – {page.name or page.id}",
                                        (wi, pi))
        self.page_combo.blockSignals(False)
        self._show_page(0)

    def _show_page(self, index: int) -> None:
        p = self.preview_profile
        where = self.page_combo.itemData(index) if index >= 0 else None
        if p is None or where is None:
            ws = p.workspaces[0] if p is not None and p.workspaces else None
            self.preview.set_view(p, ws, ws.touch_pages[0] if ws and ws.touch_pages else None)
            return
        ws = p.workspaces[where[0]]
        self.preview.set_view(p, ws, ws.touch_pages[where[1]])

    # --- Wiederherstellen --------------------------------------------------------------

    def restore(self, *_, confirm: bool = True) -> bool:
        name = self.selected_name()
        if name is None:
            return False
        if confirm and QMessageBox.question(
                self, tr("Version wiederherstellen"),
                tr("Profil auf den Stand „{version}“ zurücksetzen? Der aktuelle Stand wird "
                   "vorher als Version gesichert.", version=self.list.currentItem().text())) != \
                QMessageBox.StandardButton.Yes:
            return False
        if self._before_restore is not None:
            self._before_restore()
        try:
            self._request("versions.restore", {"id": self.profile_id, "name": name})
        except Exception as e:  # noqa: BLE001 - abgelehnt oder Dienst weg
            log.warning("Version %s nicht wiederhergestellt: %s", name, e)
            self.note.setText(tr("Wiederherstellen fehlgeschlagen: {error}", error=e))
            return False
        self.note.setText(tr("Wiederhergestellt; der vorherige Stand steht jetzt oben in der "
                              "Liste."))
        self.restored.emit(self.profile_id)
        self.reload()
        return True
