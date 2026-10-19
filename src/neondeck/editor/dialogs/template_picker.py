"""Vorlagen ankreuzen (Ersteinrichtung und „Vorlage einfügen …“).

Mehrfachauswahl, nach Gruppen sortiert und durchsuchbar. Jede angekreuzte Vorlage kommt als
eigener Arbeitsbereich ins Profil, mit einer runden Taste zum Umschalten
(``templates.insert_into``) – oder im Dialog wahlweise nur mit ihren Seiten in den offenen
Arbeitsbereich (``templates.insert_pages``).
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import N_, tr
from ...profile.templates import TemplateInfo, list_templates
from ..widgets.base import hint_label, ok_cancel_buttons

HOW = N_("Jede Vorlage kommt als eigener Arbeitsbereich in dein Profil, mit einer runden "
         "Taste zum Umschalten. Was schon da ist, bleibt.")
# Gruppen in der Liste (unbekannte Vorlagen: „Weitere“)
GROUPS = {
    N_("Craft-Apps (ArtCraft)"): ("photocraft", "lightcraft", "filmcraft", "effectcraft",
                              "vectorcraft", "soundcraft", "designcraft", "figcraft",
                              "cadcraft", "gridcraft", "deckcraft", "wordcraft", "pdfcraft"),
    N_("Kreativ & 3D"): ("grafik", "fotos", "videoschnitt", "blender", "unreal", "streaming"),
    N_("Alltag"): ("browser", "buero", "konferenz", "textbausteine", "medien", "gaming",
               "smarthome"),
    N_("System & Werkzeuge"): ("kde", "fenster", "system", "admin", "entwickler", "ziffernblock"),
}
OTHER = N_("Weitere")


def _default_hint() -> str:
    return tr("Kreuze alles an, wofür du den CT nutzt. {how} Später findest du das jederzeit "
              "wieder unter „Vorlage einfügen …“ in der Kopfzeile.", how=tr(HOW))


class TemplateChooser(QWidget):
    def __init__(self, hint: str | None = None, parent=None) -> None:
        super().__init__(parent)
        label = hint_label(hint or _default_hint())
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Suchen (Name, Programm, Inhalt) …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.templates: list[TemplateInfo] = []
        # Zeilen statt Eintraege merken (Lektion L-2026-10-18-03: keine Wrapper von Eintraegen
        # halten, die die Liste besitzt); die Liste aendert sich nach dem Aufbau nicht mehr
        self._rows: dict[str, int] = {}
        self._header_rows: list[tuple[int, list[str]]] = []
        by_id = {t.id: t for t in list_templates()}
        groups = [(g, [by_id[i] for i in ids if i in by_id]) for g, ids in GROUPS.items()]
        known = {i for ids in GROUPS.values() for i in ids}
        groups.append((OTHER, [t for t in by_id.values() if t.id not in known]))
        for group, members in groups:
            if not members:
                continue
            header = QListWidgetItem(tr(group))
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self.list.addItem(header)
            self._header_rows.append((self.list.count() - 1, [t.id for t in members]))
            for t in sorted(members, key=lambda t: t.name.casefold()):
                item = QListWidgetItem(t.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setToolTip(t.description)
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self.list.addItem(item)
                self.templates.append(t)
                self._rows[t.id] = self.list.count() - 1
        self.list.currentItemChanged.connect(lambda item, _old: self._describe(item))
        self.list.itemActivated.connect(self._toggle)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.description)
        if self.templates:
            self.list.setCurrentRow(self._rows[self.templates[0].id])

    def _item(self, template_id: str) -> QListWidgetItem:
        return self.list.item(self._rows[template_id])

    def _describe(self, item: QListWidgetItem | None) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        t = next((t for t in self.templates if t.id == tid), None)
        self.description.setText(t.description if t else "")

    def _filter(self, text: str) -> None:
        words = text.casefold().split()
        visible = set()
        for t in self.templates:
            hay = f"{t.name} {t.description} {t.id}".casefold()
            if all(w in hay for w in words):
                visible.add(t.id)
            self._item(t.id).setHidden(t.id not in visible)
        for row, ids in self._header_rows:
            self.list.item(row).setHidden(not visible.intersection(ids))

    def visible_ids(self) -> list[str]:
        """Vorlagen, die die Suche gerade zeigt."""
        return [t.id for t in self.templates if not self._item(t.id).isHidden()]

    @staticmethod
    def _toggle(item: QListWidgetItem) -> None:
        if item.data(Qt.ItemDataRole.UserRole) is None:
            return  # Gruppenueberschrift
        checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

    def chosen(self) -> list[str]:
        """Angekreuzte Vorlagen in Listenreihenfolge."""
        return [t.id for t in self.templates
                if self._item(t.id).checkState() == Qt.CheckState.Checked]

    def choose(self, template_ids: Iterable[str]) -> None:
        wanted = set(template_ids)
        for t in self.templates:
            self._item(t.id).setCheckState(Qt.CheckState.Checked if t.id in wanted
                                           else Qt.CheckState.Unchecked)


class TemplateDialog(QDialog):
    def __init__(self, profile_name: str, workspace_name: str | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Vorlage einfügen"))
        self.resize(680, 640)
        self.chooser = TemplateChooser(tr("In „{name}“ einfügen. Bestehendes bleibt.", name=profile_name))
        self.as_workspace = QRadioButton(tr("Als eigener Arbeitsbereich – mit Reglern, Rad und "
                                            "einer runden Taste zum Umschalten"))
        self.as_pages = QRadioButton(
            tr("Nur die Seiten, in den Arbeitsbereich „{name}“", name=workspace_name)
            if workspace_name else tr("Nur die Seiten, in den offenen Arbeitsbereich"))
        self.as_pages.setEnabled(workspace_name is not None)
        self.as_workspace.setChecked(True)
        self._mode = QButtonGroup(self)
        self._mode.addButton(self.as_workspace)
        self._mode.addButton(self.as_pages)
        buttons = ok_cancel_buttons(self)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText(tr("Einfügen"))
        self.ok_button.setEnabled(False)
        self.chooser.list.itemChanged.connect(
            lambda _i: self.ok_button.setEnabled(bool(self.chooser.chosen())))
        layout = QVBoxLayout(self)
        layout.addWidget(self.chooser, 1)
        layout.addWidget(self.as_workspace)
        layout.addWidget(self.as_pages)
        layout.addWidget(buttons)

    def chosen(self) -> list[str] | None:
        return self.chooser.chosen() or None

    def pages_only(self) -> bool:
        return self.as_pages.isChecked()
