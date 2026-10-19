"""Inspector fuer Tasten (Touch, rund, eckig): Tippen + Bild, Doppeltippen/Halten, Zustände."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import N_, tr
from ...device.layout import ControlKind
from ...engine.painter import action_label
from ...profile.model import Assignment, ButtonImage, StateDef
from .action_form import ActionForm
from .base import EditorWidget, combo, group_box, hint_label
from .image_editor import ImageEditor
from .list_detail import ListDetailEditor
from .nav_targets import NavTargets
from .param_widgets import AppPicker

MAX_STATES = 8
STATE_LIST_WIDTH = 140
SOURCES = [("manual", N_("Manuell (Drücken schaltet weiter)")),
           ("mute", N_("Ton stumm (Standardausgang)")),
           ("mic_mute", N_("Mikrofon stumm (Standardeingang)")),
           ("media", N_("Medien spielen")),
           ("app_running", N_("Anwendung läuft")),
           ("external", N_("Extern (CLI/API „state“)"))]
FLAG_HINT = N_("Zustand 1 = nein, Zustand 2 = ja; solange unbekannt, gilt das Grundbild.")
SOURCE_HINTS = {
    "manual": N_("Drücken führt die Aktion des Zustands aus (sonst die Grundaktion) und "
                 "schaltet weiter."),
    "external": N_("Nur „neondeck-ct state …“ bzw. die API setzt den Zustand."),
    "mute": FLAG_HINT, "mic_mute": FLAG_HINT, "media": FLAG_HINT, "app_running": FLAG_HINT,
}
NO_STATES_HINT = N_("Mit Zuständen zeigt die Taste je nach Zustand ein anderes Bild.")


class StatesEdit(ListDetailEditor):
    """Zustände (keine oder 2–8) mit Quelle; je Zustand Bild (Touch) und eigene Aktion. Die
    Zahl kommt aus der Auswahl, die Liste waehlt nur den Zustand."""

    def __init__(self, touch: bool, targets: NavTargets | None, parent=None) -> None:
        super().__init__(None, parent)
        self._noun = tr("Zustand")
        self._base = ButtonImage()
        self.count_combo = combo([(0, tr("Keine"))] + [(n, str(n)) for n in range(2, MAX_STATES + 1)])
        self.count_combo.currentIndexChanged.connect(self._count_changed)
        self.source_combo = combo([(v, tr(t)) for v, t in SOURCES])
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        self.app_picker = AppPicker(targets.catalog if targets else None)
        self.app_picker.changed.connect(self._emit)
        self.source_hint = hint_label()
        form = QFormLayout()
        form.addRow(tr("Zustände:"), self.count_combo)
        form.addRow(tr("Quelle:"), self.source_combo)
        self._app_label = QLabel(tr("Anwendung:"))
        form.addRow(self._app_label, self.app_picker)
        form.addRow(self.source_hint)
        self.list.setMaximumWidth(STATE_LIST_WIDTH)
        self.image_editor = ImageEditor(ControlKind.TOUCH, tr("Bild des Zustands")) if touch else None
        if self.image_editor is not None:
            self.image_editor.changed.connect(self.item_edited)
        self.action_form = ActionForm("press", targets=targets)
        self.action_form.changed.connect(self.item_edited)
        detail = QHBoxLayout()
        detail.addWidget(self.list)
        if self.image_editor is not None:
            detail.addWidget(self.image_editor, 1)
        detail.addWidget(group_box(tr("Eigene Aktion (leer = Grundaktion)"), self.action_form), 1)
        self._detail = QWidget()
        self._detail.setLayout(detail)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._detail, 1)

    # --- ListDetailEditor ----------------------------------------------------------------

    def item_label(self, row: int, item: StateDef) -> str:
        return tr("Zustand {n}", n=row + 1)

    def show_item(self, item: StateDef | None, valid: bool) -> None:
        state = item or StateDef()
        if self.image_editor is not None:
            self.image_editor.set_image(state.image)
        self.action_form.set_value(state.action)
        self._detail.setVisible(bool(self._items))
        self._detail.setEnabled(valid)

    def read_item(self, item: StateDef) -> StateDef:
        if self.image_editor is not None:
            item.image = self.image_editor.image()
        item.action = self.action_form.value()
        return item

    # --- Werte ------------------------------------------------------------------

    def set_value(self, a: Assignment | None) -> None:
        with self.loading():
            self._base = copy.deepcopy(a.image) if a else ButtonImage()
            src = (a.state_source if a else None) or {}
            n = len(a.states) if a else 0
            self.count_combo.setCurrentIndex(max(0, self.count_combo.findData(n)))
            i = self.source_combo.findData(src.get("type") or "manual")
            self.source_combo.setCurrentIndex(max(0, i))
            self.app_picker.set_value(src.get("app") or "")
            self.set_items(a.states if a else [])
        self._show_source()

    def set_base_image(self, img: ButtonImage) -> None:
        """Grundbild (Vorlage fuer neu angelegte Zustände)."""
        self._base = copy.deepcopy(img)

    def states(self) -> list[StateDef]:
        return self.items()

    def source(self) -> dict | None:
        if not self._items:
            return None
        t = self.source_combo.currentData()
        if t == "app_running":
            return {"type": t, "app": str(self.app_picker.value() or "").strip()}
        return {"type": t}

    # --- Ablauf -----------------------------------------------------------------

    def _count_changed(self) -> None:
        if self.is_loading:
            return
        n = self.count_combo.currentData() or 0
        del self._items[n:]
        while len(self._items) < n:
            self._items.append(StateDef(copy.deepcopy(self._base)))
        self.rebuild(min(max(0, self.list.currentRow()), n - 1))
        self._show_source()
        self.changed.emit()

    def _source_changed(self) -> None:
        self._show_source()
        self._emit()

    def _show_source(self) -> None:
        has = bool(self._items)
        t = self.source_combo.currentData()
        self.source_combo.setEnabled(has)
        self.app_picker.setVisible(has and t == "app_running")
        self._app_label.setVisible(has and t == "app_running")
        hint = SOURCE_HINTS.get(t, "") if has else NO_STATES_HINT
        self.source_hint.setText(tr(hint))


class ButtonInspector(EditorWidget, QTabWidget):
    """Reiter: „Tippen“ (Aktion, bei Touch mit Bild), „Doppeltippen & Halten“, „Zustände“."""

    def __init__(self, touch: bool, a: Assignment | None, targets: NavTargets | None,
                 parent=None) -> None:
        super().__init__(parent)
        self._touch = touch
        self.image_editor: ImageEditor | None = None
        self.label_edit: QLineEdit | None = None
        self._image = copy.deepcopy(a.image) if a else ButtonImage()
        with self.loading():
            self.action_form = ActionForm("press", live=touch, targets=targets)
            self.action_form.set_value(a.action if a else None)
            self.action_form.changed.connect(self._action_changed)
            self.addTab(self._tap_tab(a), tr("Tippen"))
            self.double_form = self._form(targets, a.double if a else None)
            self.hold_form = self._form(targets, a.hold if a else None)
            gestures = QWidget()
            row = QHBoxLayout(gestures)
            row.addWidget(group_box(tr("Doppeltippen"), self.double_form), 1)
            row.addWidget(group_box(tr("Halten"), self.hold_form), 1)
            self.addTab(gestures, tr("Doppeltippen && Halten"))
            self.states_edit = StatesEdit(touch, targets)
            self.states_edit.set_value(a)
            self.states_edit.changed.connect(self._emit)
            self.addTab(self.states_edit, tr("Zustände"))
        self._update_fallback()

    def _form(self, targets: NavTargets | None, action: dict | None) -> ActionForm:
        form = ActionForm("press", targets=targets)
        form.set_value(action)
        form.changed.connect(self._emit)
        return form

    def _tap_tab(self, a: Assignment | None) -> QWidget:
        """Touch: Aktion + Bild; Tasten ohne Display: Bezeichnung + Aktion."""
        main = QWidget()
        row = QHBoxLayout(main)
        if self._touch:
            row.addWidget(group_box(tr("Aktion"), self.action_form), 1)
            self.image_editor = ImageEditor(ControlKind.TOUCH)
            self.image_editor.set_image(a.image if a else None)
            self.image_editor.changed.connect(self._image_changed)
            row.addWidget(self.image_editor, 1)
            return main
        # Tasten ohne Display: nur die Bezeichnung (Editor-Anzeige, Ruecktext)
        self.label_edit = QLineEdit(self._image.text)
        self.label_edit.setPlaceholderText(tr("leer = Name der Aktion"))
        self.label_edit.textChanged.connect(self._label_changed)
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.addRow(tr("Bezeichnung:"), self.label_edit)
        col.addLayout(form)
        col.addWidget(group_box(tr("Aktion"), self.action_form), 1)
        row.addWidget(box, 1)
        return main

    def image(self) -> ButtonImage:
        return self.image_editor.image() if self.image_editor else copy.deepcopy(self._image)

    def value(self) -> Assignment | None:
        action = self.action_form.value()
        img = self.image()
        double, hold = self.double_form.value(), self.hold_form.value()
        states, source = self.states_edit.states(), self.states_edit.source()
        extras = double or hold or states
        if action is None and not extras and (not self._touch or img == ButtonImage()):
            return None
        return Assignment(action or {}, img, double=double, hold=hold, states=states,
                          state_source=source)

    def _label_changed(self, text: str) -> None:
        self._image.text = text
        self._emit()

    def _update_fallback(self) -> None:
        if self.image_editor is not None:
            action = self.action_form.value() or {}
            self.image_editor.set_fallback_text(action_label(action) if action.get("type")
                                                else "")

    def _action_changed(self) -> None:
        self._update_fallback()
        self._emit()

    def _image_changed(self) -> None:
        self.states_edit.set_base_image(self.image())
        self._emit()

