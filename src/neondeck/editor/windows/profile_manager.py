"""Dialog: Profile und Arbeitsbereiche verwalten, Windows-Profile (.lp5) importieren.

Nur Listen, Knoepfe und Rueckfragen; was am Profil passiert, macht ``editing.profile_ops``.
Im Editor-Prozess sind Engine und Speicher die API-Gegenstuecke (``editor.remote``); das
Aufraeumen nicht mehr benutzter Import-Ordner macht der Dienst beim Loeschen
(``remove_unused_imports``).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from ...core.i18n import tr
from ...profile.model import Profile, Workspace
from ...profile.store import PROFILE_LOAD_ERRORS
from ..dialogs.import_report import ImportReport
from ..editing.profile_ops import ProfileOps
from ..widgets.base import close_buttons, disposing, push_button

if TYPE_CHECKING:
    from ...api.contracts import EditorBackend, ProfileRepository

log = logging.getLogger(__name__)

ID_ROLE = Qt.ItemDataRole.UserRole
READABLE_ROLE = Qt.ItemDataRole.UserRole + 1
DIALOG_SIZE = (880, 480)  # Platz fuer die Listen auch mit breiteren Theme-Knoepfen
GROUP_GAP = 12


def _group(title: str, listw: QListWidget, buttons: list) -> QGroupBox:
    """Liste mit Knopfspalte daneben (``None`` = Abstand)."""
    box = QGroupBox(title)
    col = QVBoxLayout()
    for b in buttons:
        if b is None:
            col.addSpacing(GROUP_GAP)
        else:
            col.addWidget(b)
    col.addStretch(1)
    row = QHBoxLayout(box)
    row.addWidget(listw, 1)
    row.addLayout(col)
    return box


def _lp5_filter() -> str:
    return tr("Loupedeck-Profil (*.lp5)")


def _ask_name(parent, title: str, label: str, text: str = "") -> str | None:
    name, ok = QInputDialog.getText(parent, title, label, text=text)
    return name.strip() if ok and name.strip() else None


def _confirm(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


class ProfileManager(QDialog):
    """Profile anlegen/umbenennen/duplizieren/loeschen/importieren, Arbeitsbereiche pflegen."""

    changed = Signal()  # nach jeder Aenderung (Fenster zieht Profil-/Arbeitsbereichsliste nach)

    def __init__(self, store: ProfileRepository, engine: EditorBackend,
                 commit: Callable[[Profile], None],
                 switch_profile: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.ops = ProfileOps(store, engine, commit, switch_profile)
        self._home_id: str | None = None
        self.setWindowTitle(tr("Profile und Arbeitsbereiche"))
        self.resize(*DIALOG_SIZE)
        top = QHBoxLayout()
        top.addWidget(self._build_profiles(), 1)
        top.addWidget(self._build_workspaces(), 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top, 1)
        layout.addWidget(close_buttons(self))
        self._reload(self.ops.active_id)

    def _build_profiles(self) -> QGroupBox:
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(lambda _row: self._fill_workspaces())
        self.new_profile_button = push_button("document-new", tr("Neu …"), self.new_profile)
        self.rename_profile_button = push_button("edit-rename", tr("Umbenennen …"),
                                                 self.rename_profile)
        self.duplicate_profile_button = push_button("edit-copy", tr("Duplizieren …"),
                                                    self.duplicate_profile)
        self.delete_profile_button = push_button("edit-delete", tr("Löschen …"), self.delete_profile)
        self.import_button = push_button("document-import", tr("Windows-Profil importieren …"),
                                         self.import_profile)
        return _group(tr("Profile"), self.profile_list, [
            self.new_profile_button, self.rename_profile_button, self.duplicate_profile_button,
            self.delete_profile_button, None, self.import_button])

    def _build_workspaces(self) -> QGroupBox:
        self.workspace_list = QListWidget()
        self.workspace_list.currentRowChanged.connect(self._update_buttons)
        self.workspace_list.itemDoubleClicked.connect(lambda _i: self.rename_workspace())
        self.new_workspace_button = push_button("list-add", tr("Neu …"), self.new_workspace)
        self.rename_workspace_button = push_button("edit-rename", tr("Umbenennen …"),
                                                   self.rename_workspace)
        self.delete_workspace_button = push_button("list-remove", tr("Löschen …"),
                                                   self.delete_workspace)
        self.up_button = push_button("go-up", tr("Nach oben"), lambda: self.move_workspace(-1))
        self.down_button = push_button("go-down", tr("Nach unten"), lambda: self.move_workspace(1))
        self.home_button = push_button("go-home", tr("Als Heim-Arbeitsbereich"), self.set_home)
        self.home_button.setToolTip(tr("Mit diesem Arbeitsbereich startet das Profil"))
        self.workspace_box = _group(tr("Arbeitsbereiche"), self.workspace_list, [
            self.new_workspace_button, self.rename_workspace_button,
            self.delete_workspace_button, None, self.up_button, self.down_button, None,
            self.home_button])
        return self.workspace_box

    # --- Listen -----------------------------------------------------------------------

    def profile_ids(self) -> list[str]:
        return [self.profile_list.item(i).data(ID_ROLE) for i in range(self.profile_list.count())]

    def current_pid(self) -> str | None:
        item = self.profile_list.currentItem()
        return item.data(ID_ROLE) if item else None

    def select_profile(self, pid: str) -> None:
        self.profile_list.setCurrentRow(self.profile_ids().index(pid))

    def _current_ws_id(self) -> str | None:
        item = self.workspace_list.currentItem()
        return item.data(ID_ROLE) if item else None

    def _profile_item(self, pid: str, active: str) -> QListWidgetItem:
        name, ok = self.ops.name(pid)
        item = QListWidgetItem(name + (tr(" (aktiv)") if pid == active else "")
                               + ("" if ok else tr(" – kaputt")))
        item.setData(ID_ROLE, pid)
        item.setData(READABLE_ROLE, ok)
        item.setToolTip(pid)
        if pid == active:
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
        return item

    def _reload(self, select: str | None = None, ws_select: str | None = None) -> None:
        ids, active = self.ops.ids(), self.ops.active_id
        with QSignalBlocker(self.profile_list):
            self.profile_list.clear()
            for pid in ids:
                self.profile_list.addItem(self._profile_item(pid, active))
            self.profile_list.setCurrentRow(ids.index(select if select in ids else active))
        self._fill_workspaces(ws_select)

    def _fill_workspaces(self, select: str | None = None) -> None:
        pid = self.current_pid()
        profile = self._profile(pid, quiet=True) if pid else None
        self._home_id = profile.home_workspace if profile else None
        workspaces = profile.workspaces if profile else []
        with QSignalBlocker(self.workspace_list):
            self.workspace_list.clear()
            for ws in workspaces:
                item = QListWidgetItem(ws.name or ws.id)
                if ws.id == self._home_id:
                    item.setIcon(QIcon.fromTheme("go-home"))
                    item.setText(tr("{name} (Heim)", name=ws.name or ws.id))
                item.setData(ID_ROLE, ws.id)
                self.workspace_list.addItem(item)
            ids = [w.id for w in workspaces]
            if ids:
                self.workspace_list.setCurrentRow(ids.index(select) if select in ids else 0)
        name = (profile.name or profile.id) if profile else ""
        self.workspace_box.setTitle(tr("Arbeitsbereiche von „{name}“", name=name) if name else
                                    tr("Arbeitsbereiche"))
        self._update_buttons()

    def _update_buttons(self, *_) -> None:
        item = self.profile_list.currentItem()
        readable = bool(item and item.data(READABLE_ROLE))
        for b in (self.rename_profile_button, self.duplicate_profile_button):
            b.setEnabled(readable)
        self.delete_profile_button.setEnabled(self.current_pid() is not None
                                              and self.profile_list.count() > 1)
        row, n = self.workspace_list.currentRow(), self.workspace_list.count()
        self.new_workspace_button.setEnabled(readable)
        self.rename_workspace_button.setEnabled(row >= 0)
        self.delete_workspace_button.setEnabled(row >= 0 and n > 1)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < n - 1)
        self.home_button.setEnabled(row >= 0 and self._current_ws_id() != self._home_id)

    # --- Hilfen ----------------------------------------------------------------------------

    def _profile(self, pid: str | None, quiet: bool = False) -> Profile | None:
        if pid is None:
            return None
        try:
            return self.ops.profile(pid)
        except PROFILE_LOAD_ERRORS as e:
            if not quiet:
                QMessageBox.warning(self, tr("Profil"),
                                    tr("Profil „{id}“ ist nicht lesbar: {error}", id=pid,
                                       error=e))
            return None

    def _ws(self) -> tuple[Profile | None, Workspace | None]:
        profile = self._profile(self.current_pid())
        ws_id = self._current_ws_id()
        ws = next((w for w in profile.workspaces if w.id == ws_id), None) if profile else None
        return profile, ws

    def _done(self, select: str | None = None, ws_select: str | None = None) -> None:
        self._reload(select, ws_select)
        self.changed.emit()

    # --- Profile ----------------------------------------------------------------------------

    def new_profile(self) -> None:
        name = _ask_name(self, tr("Neues Profil"), tr("Name:"))
        if name:
            self._done(self.ops.new_profile(name).id)

    def rename_profile(self) -> None:
        profile = self._profile(self.current_pid())
        name = _ask_name(self, tr("Profil umbenennen"), tr("Name:"), profile.name) if profile else None
        if name:
            self.ops.rename_profile(profile, name)
            self._done(profile.id)

    def duplicate_profile(self) -> None:
        profile = self._profile(self.current_pid())
        name = _ask_name(self, tr("Profil duplizieren"), tr("Name der Kopie:"),
                         tr("{name} (Kopie)", name=profile.name or profile.id)) \
            if profile else None
        if name:
            self._done(self.ops.duplicate_profile(profile, name).id)

    def delete_profile(self) -> None:
        pid = self.current_pid()
        if not self.ops.can_delete(pid):
            return  # das letzte Profil bleibt
        name = self.ops.name(pid)[0]
        if not _confirm(self, tr("Profil löschen"),
                        tr("Das Profil „{name}“ mit allen Belegungen wirklich löschen?",
                           name=name)):
            return
        error = self.ops.delete_profile(pid, name)
        if error is not None:
            QMessageBox.warning(self, tr("Profil löschen"), error)
            return
        self._done()

    def import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Windows-Profil importieren"),
                                              str(Path.home()), _lp5_filter())
        if not path:
            return
        try:
            profile, messages = self.ops.import_lp5(Path(path))
        except (ValueError, OSError) as e:
            log.warning("Import von %s fehlgeschlagen: %s", path, e)
            QMessageBox.warning(self, tr("Import fehlgeschlagen"), str(e))
            return
        self._done(profile.id)
        with disposing(ImportReport(profile.name, messages, self)) as report:
            report.exec()

    # --- Arbeitsbereiche ----------------------------------------------------------------------

    def new_workspace(self) -> None:
        profile = self._profile(self.current_pid())
        name = _ask_name(self, tr("Neuer Arbeitsbereich"), tr("Name:")) if profile else None
        if name:
            self._done(profile.id, self.ops.new_workspace(profile, name).id)

    def rename_workspace(self) -> None:
        profile, ws = self._ws()
        name = _ask_name(self, tr("Arbeitsbereich umbenennen"), tr("Name:"), ws.name) if ws else None
        if name:
            self.ops.rename_workspace(profile, ws, name)
            self._done(profile.id, ws.id)

    def delete_workspace(self) -> None:
        profile, ws = self._ws()
        if ws is None or len(profile.workspaces) <= 1:
            return  # der letzte Arbeitsbereich bleibt
        if _confirm(self, tr("Arbeitsbereich löschen"),
                    tr("Den Arbeitsbereich „{name}“ mit allen Seiten und "
                       "Reglerbelegungen wirklich löschen?", name=ws.name or ws.id)):
            self.ops.delete_workspace(profile, ws)
            self._done(profile.id)

    def move_workspace(self, delta: int) -> None:
        profile, ws = self._ws()
        if ws is not None and self.ops.move_workspace(profile, ws, delta):
            self._done(profile.id, ws.id)

    def set_home(self) -> None:
        profile, ws = self._ws()
        if ws is not None:
            self.ops.set_home(profile, ws)
            self._done(profile.id, ws.id)
