"""Symbolauswahl: Original-Grafiken nach Gruppen, Suche, eigene Datei.

Der Katalog hat ueber 2000 Bilder; die Vorschaubildchen werden erst gezeichnet, wenn
die Liste sie anzeigt (``IconModel.data``), und in einem kleinen Zwischenspeicher gehalten.
Sie liegen auf Schwarz wie die Tasten am Geraet (die Grafiken sind hell).
"""
from __future__ import annotations

import logging
import os.path
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QImageReader, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from ...core.assets import IconEntry, catalog, resolve
from ...core.i18n import tr
from .base import disposing, ok_cancel_buttons

log = logging.getLogger(__name__)

THUMB = 64
CELL = QSize(116, 100)
CACHE_SIZE = 600            # Vorschaubildchen im Speicher (etwa vier volle Seiten)
GROUP_WIDTH = 190
DIALOG_SIZE = (820, 560)
SVG_FILL = 0.8               # SVG-Symbol fuellt so viel des Vorschauquadrats
REF_ROLE = Qt.ItemDataRole.UserRole

Resolver = Callable[[str], Path | None]


def _word_start(name: str, i: int) -> bool:
    """Beginnt bei ``name[i]`` ein Wort (Grossbuchstabe, Ziffer, nach Trennzeichen)?"""
    if not 0 < i < len(name):
        return False
    c = name[i]
    return c.isupper() or c.isdigit() or not name[i - 1].isalnum()


def display_names(names: list[str]) -> list[str]:
    """Gemeinsamen Anfang aller Namen weglassen (``AdobePsBrush`` -> ``Brush``), damit die
    kurze Beschriftung den Unterschied zeigt. Geschnitten wird nur an einer Wortgrenze,
    und jeder Name behaelt einen Rest."""
    if len(names) < 2:
        return list(names)
    n = len(os.path.commonprefix(names))
    while n >= 2 and not all(_word_start(x, n) for x in names):
        n -= 1
    return [x[n:] for x in names] if n >= 2 else list(names)


def render_thumb(path: Path | None, size: int = THUMB) -> QPixmap:
    """Bild eingepasst und mittig auf schwarzem Quadrat; unlesbar -> nur Schwarz."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.black)
    if path is None:
        return pix
    p = QPainter(pix)
    try:
        if path.suffix.lower() == ".svg":
            renderer = QSvgRenderer(QByteArray(path.read_bytes()))
            if renderer.isValid():
                ds = renderer.defaultSize()
                if ds.width() <= 0 or ds.height() <= 0:
                    ds = renderer.viewBox().size()
                if ds.width() > 0 and ds.height() > 0:
                    scale = size * SVG_FILL / max(ds.width(), ds.height())
                    w, h = ds.width() * scale, ds.height() * scale
                    renderer.render(p, QRectF((size - w) / 2, (size - h) / 2, w, h))
        else:
            reader = QImageReader(str(path))
            src = reader.size()
            if src.isValid():
                reader.setScaledSize(src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
            img = reader.read()
            if not img.isNull():
                p.drawImage((size - img.width()) // 2, (size - img.height()) // 2, img)
    except OSError as e:
        log.debug("Vorschau von %s nicht lesbar: %s", path, e)
    finally:
        p.end()
    return pix


class IconModel(QAbstractListModel):
    """Liste von ``IconEntry``; Vorschau wird beim ersten Abruf gezeichnet."""

    def __init__(self, resolver: Resolver = resolve, parent=None):
        super().__init__(parent)
        self._resolver = resolver
        self._entries: list[IconEntry] = []
        self._labels: list[str] = []
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.rendered = 0  # gezeichnete Vorschauen (Test der Faulheit)

    def set_entries(self, entries: list[IconEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._labels = display_names([e.name for e in self._entries])
        self.endResetModel()

    def entry(self, row: int) -> IconEntry:
        return self._entries[row]

    def refs(self) -> list[str]:
        return [e.ref for e in self._entries]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008  # Qt-Signatur
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        e = self._entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._labels[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{e.name}\n{tr(e.group)}"
        if role == Qt.ItemDataRole.DecorationRole:
            return self._thumb(e.ref)
        if role == REF_ROLE:
            return e.ref
        return None

    def _thumb(self, ref: str) -> QPixmap:
        pix = self._cache.get(ref)
        if pix is not None:
            self._cache.move_to_end(ref)
            return pix
        pix = render_thumb(self._resolver(ref))
        self.rendered += 1
        self._cache[ref] = pix
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return pix


def _image_filter() -> str:
    return tr("Bilder (*.png *.svg *.jpg *.jpeg *.bmp *.gif *.webp)")


class IconPicker(QDialog):
    """Dialog; nach ``exec`` liefert ``selected_ref`` die Bildreferenz (``lib:``/``svg:``/``file:``)."""

    def __init__(self, current: str | None = None, parent=None, *,
                 entries: list[IconEntry] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Symbol wählen"))
        self.resize(*DIALOG_SIZE)
        self._entries = catalog() if entries is None else list(entries)
        self._own: str | None = None
        groups: dict[str, list[IconEntry]] = {}
        for e in self._entries:
            groups.setdefault(e.group, []).append(e)
        self._groups = groups
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Symbol suchen (alle Gruppen) …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh)
        self.group_list = QListWidget()
        for name in groups:
            item = QListWidgetItem(tr(name))  # Anzeige uebersetzt, Schluessel in UserRole
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.group_list.addItem(item)
        self.group_list.currentRowChanged.connect(self._refresh)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.group_list)
        splitter.addWidget(self._build_view())
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([GROUP_WIDTH, self.width() - GROUP_WIDTH])
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(splitter, 1)
        layout.addLayout(self._build_bottom())
        self._select_current(current)
        self.search.setFocus()

    def _build_view(self) -> QListView:
        self.model = IconModel(parent=self)
        self.view = QListView()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setUniformItemSizes(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setIconSize(QSize(THUMB, THUMB))
        self.view.setGridSize(CELL)
        self.view.setWordWrap(False)  # einzeilig, sonst kuerzt ElideLeft auf „…“
        self.view.setTextElideMode(Qt.TextElideMode.ElideLeft)  # das Ende unterscheidet
        self.view.setModel(self.model)
        self.view.selectionModel().currentChanged.connect(self._update_buttons)
        self.view.doubleClicked.connect(self.accept)
        return self.view

    def _build_bottom(self) -> QHBoxLayout:
        self.count_label = QLabel()
        self.file_button = QPushButton(tr("Eigene Datei …"))
        self.file_button.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_DialogOpenButton))
        self.file_button.clicked.connect(self._own_file)
        buttons = ok_cancel_buttons(self)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        bottom = QHBoxLayout()
        bottom.addWidget(self.file_button)
        bottom.addWidget(self.count_label, 1)
        bottom.addWidget(buttons)
        return bottom

    # --- Anzeige ---------------------------------------------------------------------

    def _select_current(self, current: str | None) -> None:
        entry = next((e for e in self._entries if e.ref == current), None)
        names = list(self._groups)
        row = names.index(entry.group) if entry else 0
        if names:
            self.group_list.setCurrentRow(row)  # fuellt die Liste
        else:
            self._refresh()
        if entry:
            i = self.model.refs().index(entry.ref)
            index = self.model.index(i)
            self.view.setCurrentIndex(index)
            self.view.scrollTo(index, QListView.ScrollHint.PositionAtCenter)
        self._update_buttons()

    def _refresh(self, *_) -> None:
        words = self.search.text().casefold().split()
        if words:
            shown = [e for e in self._entries if all(w in e.name.casefold() for w in words)]
            where = tr("in allen Gruppen")
        else:
            group = self.current_group()
            shown = self._groups.get(group, []) if group else []
            where = tr("in „{group}“", group=tr(group)) if group else ""
        self.model.set_entries(shown)
        if not self._entries:
            self.count_label.setText(
                tr("Keine Grafiken gefunden – tools/import_assets.py ausführen"))
        else:
            self.count_label.setText(tr("{count} Symbole {where}", count=len(shown),
                                        where=where).strip())
        self._update_buttons()

    def _update_buttons(self, *_) -> None:
        self.ok_button.setEnabled(self.view.currentIndex().isValid())

    def _own_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Eigenes Symbol wählen"),
                                              str(Path.home()), _image_filter())
        if path:
            self._own = f"file:{path}"
            self.accept()

    # --- Abfragen ----------------------------------------------------------------------

    def group_names(self) -> list[str]:
        return list(self._groups)

    def current_group(self) -> str | None:
        item = self.group_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_group(self, name: str) -> None:
        self.group_list.setCurrentRow(list(self._groups).index(name))

    def visible_refs(self) -> list[str]:
        return self.model.refs()

    def selected_ref(self) -> str | None:
        if self._own:
            return self._own
        index = self.view.currentIndex()
        return self.model.entry(index.row()).ref if index.isValid() else None

    @staticmethod
    def choose(parent=None, current: str | None = None) -> str | None:
        """Dialog modal zeigen; Abbrechen -> ``None``."""
        with disposing(IconPicker(current, parent)) as dlg:
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            return dlg.selected_ref()
