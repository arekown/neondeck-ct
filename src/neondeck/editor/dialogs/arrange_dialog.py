"""Dialog „Anordnen …“: Arbeitsbereiche und ihre Seiten per Ziehen sortieren.

Links die Arbeitsbereiche (1 … n, dahinter die runde Taste, die nach dem Sortieren dorthin
schaltet), rechts die Seiten des gewaehlten Arbeitsbereichs. Gearbeitet wird an einer Kopie;
erst „Übernehmen“ aendert das Profil (``ConfigWindow.apply_arrangement``).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ...core.i18n import N_, tr
from ...profile import arrange
from ...profile.model import Profile

HINT = N_("Zum Sortieren ziehen. Die runden Tasten, die auf Arbeitsbereiche schalten, folgen "
          "der Reihenfolge; Tasten mit anderen Aufgaben bleiben, wie sie sind.")
ID_ROLE = Qt.ItemDataRole.UserRole


def _drag_list() -> QListWidget:
    w = QListWidget()
    w.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    w.setDefaultDropAction(Qt.DropAction.MoveAction)
    w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return w


class ArrangeDialog(QDialog):
    def __init__(self, profile: Profile, workspace_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Anordnen"))
        self.resize(760, 520)
        self._profile = Profile.from_json(profile.to_json())  # Kopie
        self._pages = {w.id: [p.id for p in w.touch_pages] for w in self._profile.workspaces}
        self._filling = False
        self.workspaces = _drag_list()
        self.pages = _drag_list()
        self.workspaces.model().rowsMoved.connect(lambda *_: self._workspaces_moved())
        self.pages.model().rowsMoved.connect(lambda *_: self._pages_moved())
        self.workspaces.currentRowChanged.connect(lambda _r: self._fill_pages())
        hint = QLabel(tr(HINT))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        ws_box, page_box = QGroupBox(tr("Arbeitsbereiche")), QGroupBox(tr("Seiten"))
        QVBoxLayout(ws_box).addWidget(self.workspaces)
        QVBoxLayout(page_box).addWidget(self.pages)
        lists = QHBoxLayout()
        lists.addWidget(ws_box, 1)
        lists.addWidget(page_box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Übernehmen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(lists, 1)
        layout.addWidget(buttons)
        self._fill_workspaces(workspace_id)

    # --- Anzeige ---------------------------------------------------------------------------

    def _fill_workspaces(self, select: str | None) -> None:
        keys = {a.action.get("id"): code - 6 for code, a in self._profile.round.items()
                if a is not None and a.action.get("type") == "workspace"}
        self._filling = True
        try:
            self.workspaces.clear()
            for n, ws in enumerate(self._profile.workspaces, 1):
                text = f"{n}.  {ws.name or ws.id}"
                if ws.id in keys:
                    text += tr("   ·  runde Taste {n}", n=keys[ws.id])
                if ws.id == self._profile.home_workspace:
                    text += tr("   ·  Start")
                item = QListWidgetItem(text)
                item.setData(ID_ROLE, ws.id)
                self.workspaces.addItem(item)
        finally:
            self._filling = False
        ids = self.workspace_order()
        self.workspaces.setCurrentRow(ids.index(select) if select in ids else 0)
        self._fill_pages()

    def _fill_pages(self) -> None:
        ws = self._current_ws()
        self._filling = True
        try:
            self.pages.clear()
            for n, page in enumerate(ws.touch_pages if ws else [], 1):
                item = QListWidgetItem(f"{n}.  {page.name or page.id}")
                if page.folder:
                    item.setIcon(QIcon.fromTheme("folder"))
                    item.setToolTip(tr("Ordnerseite"))
                item.setData(ID_ROLE, page.id)
                self.pages.addItem(item)
        finally:
            self._filling = False

    def _current_ws(self):
        item = self.workspaces.currentItem()
        ws_id = item.data(ID_ROLE) if item is not None else None
        return next((w for w in self._profile.workspaces if w.id == ws_id), None)

    # --- Ziehen ----------------------------------------------------------------------------

    def _workspaces_moved(self) -> None:
        if self._filling:
            return
        current = self._current_ws()
        arrange.reorder_workspaces(self._profile, self.workspace_order())
        self._fill_workspaces(current.id if current else None)

    def _pages_moved(self) -> None:
        ws = self._current_ws()
        if self._filling or ws is None:
            return
        order = [self.pages.item(i).data(ID_ROLE) for i in range(self.pages.count())]
        arrange.reorder_pages(ws, order)
        self._pages[ws.id] = order
        row = self.pages.currentRow()
        self._fill_pages()
        self.pages.setCurrentRow(row)

    # --- Ergebnis --------------------------------------------------------------------------

    def workspace_order(self) -> list[str]:
        return [self.workspaces.item(i).data(ID_ROLE) for i in range(self.workspaces.count())]

    def page_orders(self) -> dict[str, list[str]]:
        return dict(self._pages)

    def move_workspace(self, src: int, dst: int) -> None:
        """Wie Ziehen (fuer Tests und Tastatur): Eintrag ``src`` an Stelle ``dst``."""
        self.workspaces.model().moveRow(self.workspaces.rootIndex(), src,
                                        self.workspaces.rootIndex(), dst)

    def move_page(self, src: int, dst: int) -> None:
        self.pages.model().moveRow(self.pages.rootIndex(), src, self.pages.rootIndex(), dst)
