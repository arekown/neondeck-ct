"""Inspector fuer Regler (Drehen, Drücken, Leiste, Ebenen) und Rad (Drehen, Anzeige, Tippen)."""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import N_, tr
from ...device.layout import ControlKind
from ...engine.painter import layer_name
from ...profile.model import (
    ENCODER_STRIPS,
    WHEEL_DISPLAYS,
    ButtonImage,
    Encoder,
    EncoderLayer,
    Wheel,
)
from ...profile.schema import FACTOR_RANGE
from .action_form import ActionForm
from .base import EditorWidget, combo, group_box, hint_label, select_or_add
from .image_editor import ImageEditor
from .list_detail import ListDetailEditor
from .nav_targets import NavTargets

LAYER_LIST_WIDTH = 180
# Anzeigenamen der Wertemengen aus dem Profilformat (``Encoder.strip``, ``Wheel.display``)
_STRIP_LABELS = {"name": N_("Name"), "name_value": N_("Name + Wert"), "bar": N_("Balken")}
_WHEEL_LABELS = {"clock": N_("Uhr"), "label": N_("Text"), "arc": N_("Wert-Bogen"),
                 "image": N_("Bild"), "blank": N_("Leer")}
STRIP_CHOICES = [(v, _STRIP_LABELS[v]) for v in ENCODER_STRIPS]
WHEEL_CHOICES = [(v, _WHEEL_LABELS[v]) for v in WHEEL_DISPLAYS]
TURN_MODES = [("rotate", N_("Eine Drehaktion")), ("split", N_("Links und rechts getrennt"))]
TAP_HINT = N_("Leer: Tippen auf den Leistenabschnitt wirkt wie Drücken des Reglers.")
LAYER_HINT = N_("Mit Ebenen: kurz drücken wechselt die Ebene (die Leiste zeigt sie), lang "
                "drücken löst „Drücken“ der Ebene aus.")


def _translated(choices) -> list[tuple[str, str]]:
    return [(value, tr(label)) for value, label in choices]


class TurnEditor(EditorWidget, QWidget):
    """Drehen als eine Aktion (Drehaktion mit Schritten) oder je Richtung eine Aktion."""

    def __init__(self, targets: NavTargets | None, parent=None) -> None:
        super().__init__(parent)
        self.mode_combo = combo(_translated(TURN_MODES))
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.rotate_form = ActionForm("rotate", targets=targets)
        self.left_form = ActionForm("press", targets=targets)
        self.right_form = ActionForm("press", targets=targets)
        for f in (self.rotate_form, self.left_form, self.right_form):
            f.changed.connect(self._emit)
        self._split = QWidget()
        row = QHBoxLayout(self._split)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(group_box(tr("Links"), self.left_form), 1)
        row.addWidget(group_box(tr("Rechts"), self.right_form), 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.addRow(tr("Drehen:"), self.mode_combo)
        layout.addLayout(form)
        layout.addWidget(self.rotate_form)
        layout.addWidget(self._split)
        self._show_mode()

    def set_value(self, rotate, left, right) -> None:
        with self.loading():
            split = rotate is None and (left is not None or right is not None)
            self.mode_combo.setCurrentIndex(1 if split else 0)
            self.rotate_form.set_value(rotate)
            self.left_form.set_value(left)
            self.right_form.set_value(right)
        self._show_mode()

    def split(self) -> bool:
        return self.mode_combo.currentData() == "split"

    def value(self) -> tuple[dict | None, dict | None, dict | None]:
        """``(rotate, left, right)``; die nicht gewaehlte Art bleibt leer."""
        if self.split():
            return None, self.left_form.value(), self.right_form.value()
        return self.rotate_form.value(), None, None

    def _show_mode(self) -> None:
        self.rotate_form.setVisible(not self.split())
        self._split.setVisible(self.split())

    def _mode_changed(self) -> None:
        self._show_mode()
        self._emit()


class TurnSettings(EditorWidget, QObject):
    """Gemeinsam fuer Regler und Rad: Schrittfaktor und „Richtung umkehren“; die beiden Felder
    kommen mit ``add_rows`` ins Formular des Inspectors (``parent``)."""

    def __init__(self, factor: int, invert: bool, parent: QObject) -> None:
        super().__init__(parent)
        self.factor_spin = QSpinBox()
        self.factor_spin.setRange(*FACTOR_RANGE)
        self.factor_spin.setPrefix(tr("× "))
        self.factor_spin.setValue(factor)
        self.factor_spin.setToolTip(tr("Schritte je Rastung"))
        self.factor_spin.valueChanged.connect(self._emit)
        self.invert_check = QCheckBox(tr("Richtung umkehren"))
        self.invert_check.setChecked(invert)
        self.invert_check.toggled.connect(self._emit)

    def add_rows(self, form: QFormLayout) -> None:
        form.addRow(tr("Schrittfaktor:"), self.factor_spin)
        form.addRow(self.invert_check)

    def factor(self) -> int:
        return self.factor_spin.value()

    def invert(self) -> bool:
        return self.invert_check.isChecked()


class LayersEdit(ListDetailEditor):
    """Ebenen eines Reglers: Liste (hinzufügen, entfernen, verschieben) und die gewaehlte
    Ebene (Bezeichnung, Drehen, Drücken)."""

    def __init__(self, targets: NavTargets | None, parent=None) -> None:
        super().__init__(tr("Ebene"), parent)
        self.list.setMaximumWidth(LAYER_LIST_WIDTH)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText(tr("leer = Name der Aktion"))
        self.label_edit.textChanged.connect(self.item_edited)
        self.turn = TurnEditor(targets)
        self.turn.changed.connect(self.item_edited)
        self.press_form = ActionForm("press", targets=targets)
        self.press_form.changed.connect(self.item_edited)
        self._detail = QWidget()
        d = QVBoxLayout(self._detail)
        d.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.addRow(tr("Bezeichnung:"), self.label_edit)
        d.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(group_box(tr("Drehen"), self.turn), 2)
        row.addWidget(group_box(tr("Drücken (lang)"), self.press_form), 1)
        d.addLayout(row)
        top = QHBoxLayout()
        top.addWidget(self.list)
        top.addLayout(self.buttons)
        top.addWidget(self._detail, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label(tr(LAYER_HINT)))
        layout.addLayout(top, 1)
        self._update_buttons()

    def new_item(self) -> EncoderLayer:
        return EncoderLayer()

    def item_label(self, row: int, item: EncoderLayer) -> str:
        return layer_name(row, item)

    def show_item(self, item: EncoderLayer | None, valid: bool) -> None:
        layer = item or EncoderLayer()
        self.label_edit.setText(layer.label)
        self.turn.set_value(layer.rotate, layer.left, layer.right)
        self.press_form.set_value(layer.press)
        self._detail.setEnabled(valid)

    def read_item(self, item: EncoderLayer) -> EncoderLayer:
        rotate, left, right = self.turn.value()
        return EncoderLayer(rotate, left, right, self.press_form.value(), self.label_edit.text())

    def value(self) -> list[EncoderLayer]:
        return self.items()

    def set_value(self, layers: list[EncoderLayer]) -> None:
        self.set_items(layers)


class KnobInspector(EditorWidget, QTabWidget):
    """Reiter „Drehen & Drücken“ (Bezeichnung, Leiste, Richtung, Faktor, Tippen auf die
    Leiste) und „Ebenen“."""

    def __init__(self, enc: Encoder, targets: NavTargets | None, parent=None) -> None:
        super().__init__(parent)
        with self.loading():
            self.label_edit = QLineEdit(enc.label)
            self.label_edit.setPlaceholderText(tr("leer = Name der Aktion"))
            self.label_edit.textChanged.connect(self._emit)
            self.strip_combo = combo(_translated(STRIP_CHOICES))
            select_or_add(self.strip_combo, enc.strip)
            self.strip_combo.currentIndexChanged.connect(self._emit)
            self.turn_settings = TurnSettings(enc.factor, enc.invert, self)
            self.turn_settings.changed.connect(self._emit)
            self.turn = TurnEditor(targets)
            self.turn.set_value(enc.rotate, enc.left, enc.right)
            self.turn.changed.connect(self._emit)
            self.press_form = self._form(targets, enc.press)
            self.tap_form = self._form(targets, enc.tap)
            self.addTab(self._main_tab(), tr("Drehen && Drücken"))
            self.layers_edit = LayersEdit(targets)
            self.layers_edit.set_value(enc.layers)
            self.layers_edit.changed.connect(self._emit)
            self.addTab(self.layers_edit, tr("Ebenen"))

    def _form(self, targets: NavTargets | None, action: dict | None) -> ActionForm:
        form = ActionForm("press", targets=targets)
        form.set_value(action)
        form.changed.connect(self._emit)
        return form

    def _main_tab(self) -> QWidget:
        form = QFormLayout()
        form.addRow(tr("Bezeichnung:"), self.label_edit)
        form.addRow(tr("Leiste:"), self.strip_combo)
        self.turn_settings.add_rows(form)
        tap_box = QGroupBox(tr("Tippen auf die Leiste"))
        tap_layout = QVBoxLayout(tap_box)
        tap_layout.addWidget(hint_label(tr(TAP_HINT)))
        tap_layout.addWidget(self.tap_form)
        left = QVBoxLayout()
        left.addLayout(form)
        left.addWidget(group_box(tr("Drücken"), self.press_form))
        left.addWidget(tap_box)
        left.addStretch(1)
        main = QWidget()
        row = QHBoxLayout(main)
        row.addLayout(left, 1)
        row.addWidget(group_box(tr("Drehen"), self.turn), 2)
        return main

    def value(self) -> Encoder:
        rotate, left, right = self.turn.value()
        return Encoder(rotate, self.press_form.value(), self.label_edit.text(), left=left,
                       right=right, invert=self.turn_settings.invert(),
                       factor=self.turn_settings.factor(), layers=self.layers_edit.value(),
                       strip=self.strip_combo.currentData(), tap=self.tap_form.value())


class WheelInspector(EditorWidget, QTabWidget):
    """Reiter „Drehen“, „Anzeige“ (Modus, Text, Bild) und „Tippen“ (Mitte des Raddisplays)."""

    def __init__(self, wheel: Wheel, targets: NavTargets | None, parent=None) -> None:
        super().__init__(parent)
        self._had_image = wheel.image is not None
        with self.loading():
            self.turn = TurnEditor(targets)
            self.turn.set_value(wheel.rotate, wheel.left, wheel.right)
            self.turn.changed.connect(self._emit)
            self.turn_settings = TurnSettings(wheel.factor, wheel.invert, self)
            self.turn_settings.changed.connect(self._emit)
            turn_tab = QWidget()
            form = QFormLayout()
            self.turn_settings.add_rows(form)
            t = QVBoxLayout(turn_tab)
            t.addLayout(form)
            t.addWidget(self.turn, 1)
            self.addTab(turn_tab, tr("Drehen"))
            self.addTab(self._display_tab(wheel), tr("Anzeige"))
            self.tap_form = ActionForm("press", targets=targets)
            self.tap_form.set_value(wheel.tap)
            self.tap_form.changed.connect(self._emit)
            tap = QWidget()
            QVBoxLayout(tap).addWidget(group_box(tr("Tippen auf die Mitte des Raddisplays"),
                                                 self.tap_form))
            self.addTab(tap, tr("Tippen"))
        self._show_display()

    def _display_tab(self, wheel: Wheel) -> QWidget:
        self.display_combo = combo(_translated(WHEEL_CHOICES))
        select_or_add(self.display_combo, wheel.display)
        self.display_combo.currentIndexChanged.connect(self._display_changed)
        self.label_edit = QLineEdit(wheel.label)
        self.label_edit.textChanged.connect(self._emit)
        self.image_editor = ImageEditor(ControlKind.WHEEL, tr("Bild im Rad"))
        self.image_editor.set_image(wheel.image)
        self.image_editor.changed.connect(self._emit)
        show = QWidget()
        form = QFormLayout()
        form.addRow(tr("Anzeige:"), self.display_combo)
        form.addRow(tr("Text:"), self.label_edit)
        s = QHBoxLayout(show)
        s.addLayout(form, 1)
        s.addWidget(self.image_editor, 2)
        return show

    def value(self) -> Wheel:
        rotate, left, right = self.turn.value()
        img = self.image_editor.image()
        keep = self._had_image or img != ButtonImage() or \
            self.display_combo.currentData() == "image"
        return Wheel(rotate, self.display_combo.currentData(), self.label_edit.text(),
                     left=left, right=right, invert=self.turn_settings.invert(),
                     factor=self.turn_settings.factor(), tap=self.tap_form.value(),
                     image=img if keep else None)

    def _show_display(self) -> None:
        mode = self.display_combo.currentData()
        self.image_editor.setVisible(mode == "image")
        self.label_edit.setEnabled(mode in ("label", "arc"))

    def _display_changed(self) -> None:
        self._show_display()
        self._emit()
