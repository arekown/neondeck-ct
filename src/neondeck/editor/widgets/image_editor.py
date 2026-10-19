"""Tastenbild-Editor: Vorlage, Symbol (einfaerben), Text, Schrift, Groesse, Ausrichtung,
Farben – mit Vorschau in Zielpixeln, gezeichnet wie am Geraet (``render_tile``)."""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...core.assets import resolve
from ...core.i18n import N_, tr
from ...device.layout import STRIP_WIDTH, WHEEL_SIZE, ControlKind
from ...engine.painter import image_spec
from ...profile.model import ButtonImage
from ...render import fonts
from ...render.icons import load_icon
from ...render.images import TILE, WHEEL_TILE, render_tile, wheel_tile
from .base import EditorWidget, combo, hbox, select_or_add, tool_button
from .color_button import DEFAULT_COLOR, ColorButton
from .icon_picker import IconPicker
from .qt_images import to_qimage

log = logging.getLogger(__name__)

LAYOUT_CHOICES = [("auto", N_("Automatisch")), ("icon", N_("Nur Symbol")),
                  ("icon_text", N_("Symbol + Text")), ("text", N_("Nur Text")),
                  ("big_text", N_("Großer Text"))]
ALIGN_H_CHOICES = [("left", N_("Links")), ("center", N_("Mitte")), ("right", N_("Rechts"))]
ALIGN_V_CHOICES = [("top", N_("Oben")), ("center", N_("Mitte")), ("bottom", N_("Unten"))]
SIZE_RANGE = (7, 80)
DEFAULT_FIXED_SIZE = 18
# Zielanzeige -> (Breite, Hoehe) in Pixeln
TARGETS = {ControlKind.TOUCH: (TILE, TILE), ControlKind.STRIP: (STRIP_WIDTH, TILE),
           ControlKind.WHEEL: (WHEEL_SIZE, WHEEL_SIZE)}
PREVIEW_SCALE = {ControlKind.TOUCH: 2, ControlKind.STRIP: 2, ControlKind.WHEEL: 1}


def _translated(choices) -> list[tuple[str, str]]:
    return [(value, tr(label)) for value, label in choices]


class ImageEditor(EditorWidget, QGroupBox):
    """Bild einer Taste (bzw. eines Zustands oder des Rads); ``changed`` nach jeder Aenderung.

    ``target`` bestimmt die Vorschau: ``touch`` 90×90, ``strip`` 60×90, ``wheel`` 240×240
    (Bild im Innenquadrat des runden Displays)."""

    def __init__(self, target: str = ControlKind.TOUCH, title: str | None = None, parent=None,
                 icon_loader: Callable[[str, int], object] | None = None):
        super().__init__(title or tr("Bild"), parent)
        self._target = target if target in TARGETS else ControlKind.TOUCH
        self._image = ButtonImage()
        self._fallback = ""
        self._icon_loader = icon_loader or (lambda ref, size: load_icon(ref, size, resolve))
        self._icons: dict[tuple, object] = {}
        form = QFormLayout()
        self._build_look_rows(form)
        self._build_text_rows(form)
        layout = QHBoxLayout(self)
        layout.addLayout(form, 1)
        layout.addLayout(self._build_preview())
        self._show()

    def _build_look_rows(self, form: QFormLayout) -> None:
        """Vorlage, Hintergrund, Symbol und Symbolfarbe."""
        self.layout_combo = combo(_translated(LAYOUT_CHOICES))
        self.layout_combo.currentIndexChanged.connect(self._fields_changed)
        form.addRow(tr("Vorlage:"), self.layout_combo)
        self.bg_button = ColorButton(tr("Hintergrundfarbe"))
        self.bg_button.color_chosen.connect(lambda c: self._set_color("bg", c))
        form.addRow(tr("Hintergrund:"), self.bg_button)
        self.icon_button = QPushButton(QIcon.fromTheme("insert-image"), tr("Symbol wählen …"))
        self.icon_button.clicked.connect(self.choose_icon)
        self.icon_clear_button = tool_button("edit-clear", "×", tr("Kein Symbol"),
                                             lambda: self._set_icon(None))
        self.icon_label = QLabel()
        form.addRow(tr("Symbol:"), hbox(self.icon_button, self.icon_clear_button,
                                    (self.icon_label, 1)))
        self.tint_check = QCheckBox(tr("einfärben"))
        self.tint_check.toggled.connect(self._tint_toggled)
        self.tint_button = ColorButton(tr("Symbolfarbe"))
        self.tint_button.color_chosen.connect(lambda c: self._set_color("icon_color", c))
        form.addRow(tr("Symbolfarbe:"), hbox(self.tint_check, (self.tint_button, 1)))

    def _build_text_rows(self, form: QFormLayout) -> None:
        """Text, Textfarbe, Schrift, Groesse und Ausrichtung."""
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(tr("leer = Name der Aktion, wenn kein Symbol"))
        self.text_edit.textChanged.connect(self._fields_changed)
        form.addRow(tr("Text:"), self.text_edit)
        self.text_color_button = ColorButton(tr("Textfarbe"))
        self.text_color_button.color_chosen.connect(lambda c: self._set_color("text_color", c))
        form.addRow(tr("Textfarbe:"), self.text_color_button)
        self.font_combo = combo([(None, tr("Standard (Noto Sans)"))]
                                + [(f, f) for f in fonts.FAMILIES if f != fonts.DEFAULT_FAMILY])
        self.font_combo.currentIndexChanged.connect(self._fields_changed)
        form.addRow(tr("Schrift:"), self.font_combo)
        self.size_check = QCheckBox(tr("fest"))
        self.size_check.setToolTip(tr("Aus: so groß, wie es passt"))
        self.size_check.toggled.connect(self._fields_changed)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(*SIZE_RANGE)
        self.size_spin.setSuffix(tr(" px"))
        self.size_spin.setValue(DEFAULT_FIXED_SIZE)
        self.size_spin.valueChanged.connect(self._fields_changed)
        form.addRow(tr("Größe:"), hbox(self.size_check, (self.size_spin, 1)))
        self.align_h_combo = combo(_translated(ALIGN_H_CHOICES))
        self.align_h_combo.currentIndexChanged.connect(self._fields_changed)
        self.align_v_combo = combo(_translated(ALIGN_V_CHOICES))
        self.align_v_combo.currentIndexChanged.connect(self._fields_changed)
        form.addRow(tr("Ausrichtung:"), hbox((self.align_h_combo, 1), (self.align_v_combo, 1)))

    def _build_preview(self) -> QVBoxLayout:
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.size_label = QLabel()
        self.size_label.setObjectName("hint")
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w, h = TARGETS[self._target]
        self.size_label.setText(tr("Zielgröße {w} × {h} px", w=w, h=h))
        side = QVBoxLayout()
        side.addWidget(self.preview)
        side.addWidget(self.size_label)
        side.addStretch(1)
        return side

    # --- Werte ---------------------------------------------------------------------

    def image(self) -> ButtonImage:
        return copy.deepcopy(self._image)

    def set_image(self, img: ButtonImage | None) -> None:
        self._image = copy.deepcopy(img) if img is not None else ButtonImage()
        self._show()

    def set_fallback_text(self, text: str) -> None:
        """Text, den das Geraet ohne Symbol und Text zeigt (Name der Aktion)."""
        self._fallback = text
        self._render_preview()

    def _show(self) -> None:
        img = self._image
        with self.loading():
            select_or_add(self.layout_combo, img.layout)
            self.text_edit.setText(img.text)
            if img.font:
                select_or_add(self.font_combo, img.font)
            else:
                self.font_combo.setCurrentIndex(0)
            self.size_check.setChecked(img.font_size is not None)
            if img.font_size is not None:
                self.size_spin.setValue(int(img.font_size))
            select_or_add(self.align_h_combo, img.align_h)
            select_or_add(self.align_v_combo, img.align_v)
            self.tint_check.setChecked(img.icon_color is not None)
        self._show_colors()

    def _show_colors(self) -> None:
        img = self._image
        self.bg_button.set_color(img.bg)
        self.text_color_button.set_color(img.text_color)
        self.tint_button.set_color(img.icon_color or DEFAULT_COLOR)
        self.tint_button.setEnabled(img.icon_color is not None)
        self.icon_label.setText(self._icon_name(img.icon))
        self.icon_label.setToolTip(img.icon or "")
        self.icon_clear_button.setEnabled(bool(img.icon))
        self.size_spin.setEnabled(img.font_size is not None)
        self._render_preview()

    @staticmethod
    def _icon_name(ref: str | None) -> str:
        if not ref:
            return tr("kein Symbol")
        return Path(ref.partition(":")[2]).name or ref

    def _fields_changed(self, *_) -> None:
        if self.is_loading:
            return
        img = self._image
        img.layout = self.layout_combo.currentData()
        img.text = self.text_edit.text()
        img.font = self.font_combo.currentData()
        img.font_size = self.size_spin.value() if self.size_check.isChecked() else None
        img.align_h = self.align_h_combo.currentData()
        img.align_v = self.align_v_combo.currentData()
        self._show_colors()
        self.changed.emit()

    def _tint_toggled(self, on: bool) -> None:
        if self.is_loading:
            return
        self._image.icon_color = (self._image.icon_color or DEFAULT_COLOR) if on else None
        self._show_colors()
        self.changed.emit()

    def _set_color(self, attr: str, color: str) -> None:
        setattr(self._image, attr, color)
        if attr == "icon_color":
            with self.loading():
                self.tint_check.setChecked(True)
        self._show_colors()
        self.changed.emit()

    def choose_icon(self) -> None:
        ref = IconPicker.choose(self, self._image.icon)
        if ref:
            self._set_icon(ref)

    def _set_icon(self, ref: str | None) -> None:
        self._image.icon = ref
        self._show_colors()
        self.changed.emit()

    # --- Vorschau ------------------------------------------------------------------

    def _icon(self, ref: str, size: int):
        key = (ref, size)
        if key not in self._icons:
            self._icons[key] = self._icon_loader(ref, size)
        return self._icons[key]

    def preview_image(self):
        """Bild in Zielpixeln (PIL), wie das Geraet es zeigt."""
        img = self._image
        size = WHEEL_TILE if self._target == ControlKind.WHEEL else TILE
        icon = self._icon(img.icon, size) if img.icon else None
        text = img.text if (img.text.strip() or icon is not None) else self._fallback
        spec = image_spec(img, icon, text)
        if self._target == ControlKind.WHEEL:
            return wheel_tile(spec)
        if self._target == ControlKind.STRIP:  # Leistenabschnitt: 60 breit, Bild mittig
            w, h = TARGETS[ControlKind.STRIP]
            out = Image.new("RGB", (w, h), img.bg)
            out.paste(render_tile(spec, w), (0, (h - w) // 2))
            return out
        return render_tile(spec)

    def _render_preview(self) -> None:
        try:
            pil = self.preview_image()
        except (ValueError, TypeError) as e:  # ungueltige Farbe o. Ae.
            log.warning("Vorschau nicht darstellbar: %s", e)
            self.preview.clear()
            return
        scale = PREVIEW_SCALE[self._target]
        pix = QPixmap.fromImage(to_qimage(pil))
        if scale != 1:
            pix = pix.scaled(pix.width() * scale, pix.height() * scale,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        self.preview.setPixmap(pix)
