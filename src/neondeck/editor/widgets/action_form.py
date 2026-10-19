"""Aktionsformular: Aktionstyp und seine Parameter (auch Makro-Schritte, Auswahllisten).

Nur Standard-Widgets; Farben und Schriften kommen aus dem Theme (keine Stylesheets).
Je Parameter baut ``param_factory`` eine Eingabe mit ``value``/``set_value``/``changed``:
Arbeitsbereich/Profil/Ordnerseite aus Listen (``NavTargets``), Anwendung und KDE-Kürzel aus
den Listen des Dienstes (``param_widgets.Catalog``), mehrzeilige HTTP-Kopfzeilen/Inhalte,
Makros auch als Klartext.
"""
from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from ...actions.base import Param, registry
from ...core.i18n import N_, tr
from ...engine.kinds import LIVE_TYPES
from ...ui import theme
from .action_meta import HIDDEN_TYPES, category_name, ordered_categories
from .base import EditorWidget, hint_label
from .nav_targets import NavTargets
from .param_factory import make_param_widget
from .param_widgets import PathEdit, ShortcutPicker

EMPTY_PARAM_KINDS = frozenset({"text", "file", "dir", "keys"})  # leer = nicht gespeichert
# Auswahlwerte, die „nichts einstellen“ heissen: ebenfalls nicht gespeichert
EMPTY_CHOICES = frozenset({("place", "none")})
PASTE_HINT = N_("„Einfügen“ legt den Text in die Zwischenablage und überschreibt deren Inhalt.")
CATEGORY_INDENT = "    "


class ActionForm(EditorWidget, QWidget):
    """Aktionstyp (nach Kategorie gruppiert) und das Formular seiner Parameter.

    ``kind`` ist "press" oder "rotate" (nur passende Typen); ``live`` zeigt auch
    Anzeige-Typen (Uhr, Datum, Stoppuhr) – die gibt es nur auf Touch-Tasten.
    Mit ``targets`` werden Arbeitsbereich und Profil aus einer Liste gewaehlt.
    """

    def __init__(self, kind: str = "press", *, live: bool = False,
                 targets: NavTargets | None = None, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._live = live
        self._targets = targets
        self._extra: dict = {}  # unbekannte Schluessel der geladenen Aktion (bleiben erhalten)
        self.shortcut_picker: ShortcutPicker | None = None
        self.paste_hint: QLabel | None = None
        self._fields: dict[str, tuple[Param, QWidget]] = {}
        self.type_combo = QComboBox()
        self.type_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._fill_types()
        theme.notifier.changed.connect(self._style_headers)  # Schrift folgt dem Theme
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow(tr("Aktion:"), self.type_combo)
        layout.addRow(self._form_host)

    def _types(self) -> list:
        return [at for at in registry().values()
                if at.name not in HIDDEN_TYPES and self._kind in at.kinds
                and (self._live or at.name not in LIVE_TYPES)]

    def _fill_types(self) -> None:
        combo = self.type_combo
        combo.addItem(tr("Keine Aktion"), None)
        by_cat: dict[str, list] = {}
        for at in self._types():
            by_cat.setdefault(at.category, []).append(at)
        model = combo.model()
        for cat in ordered_categories(by_cat):
            combo.addItem(category_name(cat))
            model.item(combo.count() - 1).setFlags(Qt.ItemFlag.NoItemFlags)
            for at in by_cat[cat]:
                combo.addItem(CATEGORY_INDENT + tr(at.label), at.name)
        self._style_headers()

    def _style_headers(self, *_) -> None:
        """Kategorie-Zeilen fett in der aktuellen Schrift des Auswahlfelds.

        Die Zeilen werden jedes Mal im Modell gesucht (nicht auswaehlbar = Ueberschrift), nie
        als QStandardItem aufgehoben (Lektion L-2026-10-18-03: das Modell loescht sie in C++,
        ein festgehaltener Wrapper landet sonst auf einem fremden Objekt)."""
        font = QFont(self.type_combo.font())
        font.setBold(True)
        model = self.type_combo.model()
        for row in range(model.rowCount()):
            item = model.item(row)
            if item.flags() == Qt.ItemFlag.NoItemFlags:
                item.setFont(font)

    def field(self, name: str) -> QWidget:
        """Eingabe-Widget eines Parameters (Datei/Ordner: die Textzeile)."""
        widget = self._fields[name][1]
        return widget.line if isinstance(widget, PathEdit) else widget

    def value(self) -> dict | None:
        t = self.type_combo.currentData()
        if not t:
            return None
        out: dict[str, Any] = {**copy.deepcopy(self._extra), "type": t}
        for name, (param, widget) in self._fields.items():
            v = widget.value()
            if (param.kind in EMPTY_PARAM_KINDS and v in ("", None)) \
                    or (param.kind == "choice" and isinstance(v, str)
                        and (name, v) in EMPTY_CHOICES):
                out.pop(name, None)
            else:
                out[name] = v
        return out

    def set_value(self, action: dict | None) -> None:
        action = action or {}
        t = action.get("type")
        with self.loading():
            self.type_combo.setCurrentIndex(self._type_index(t, action))
            self._build(t)
            params = {p.name for p, _ in self._fields.values()}
            self._extra = {k: copy.deepcopy(v) for k, v in action.items()
                           if k != "type" and k not in params}
            for name, (_param, widget) in self._fields.items():
                if name in action:
                    widget.set_value(action[name])
            if self.shortcut_picker is not None:
                self.shortcut_picker.set_shortcut(str(action.get("component") or ""),
                                                  str(action.get("name") or ""))
            self._show_paste_hint()

    def _type_index(self, t: str | None, action: dict) -> int:
        """Zeile des Typs ``t``; nicht waehlbare (z. B. „Nicht unterstuetzt“ aus dem Import)
        kommen als eigener Eintrag dazu."""
        i = self.type_combo.findData(t) if t else 0
        if t and i < 0:
            at = registry().get(t)
            label = tr(at.label) if at else tr("Unbekannt: {type}", type=t)
            if action.get("original"):
                label += f" ({action['original']})"
            self.type_combo.insertItem(1, label, t)
            i = 1
        return i

    def _type_changed(self) -> None:
        if self.is_loading:
            return
        self._extra = {}
        self._build(self.type_combo.currentData())
        self.changed.emit()

    def _build(self, t: str | None) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._fields = {}
        self.shortcut_picker = None
        self.paste_hint = None
        at = registry().get(t) if t else None
        if t == "kde_shortcut":
            self.shortcut_picker = ShortcutPicker(self._targets.catalog if self._targets else None)
            self.shortcut_picker.setToolTip(
                tr("Globales Kürzel aus KDE wählen (oder unten eintragen)"))
            self.shortcut_picker.changed.connect(self._shortcut_chosen)
            self._form.addRow(tr("Auswahl:"), self.shortcut_picker)
        for param in at.params if at else []:
            widget = make_param_widget(t, param, self._targets, self._nested_form)
            widget.changed.connect(self._emit)
            self._fields[param.name] = (param, widget)
            self._form.addRow(tr("{label}:", label=tr(param.label)), widget)
        if t == "text":
            self.paste_hint = hint_label(tr(PASTE_HINT))
            self._form.addRow(self.paste_hint)
            self._fields["mode"][1].currentIndexChanged.connect(self._show_paste_hint)
            self._show_paste_hint()
        self._form_host.setVisible(bool(self._fields))

    def _nested_form(self) -> ActionForm:
        """Formular eines Makro-Schritts (Druckaktion, gleiche Ziele)."""
        return ActionForm("press", targets=self._targets)

    def _show_paste_hint(self, *_) -> None:
        if self.paste_hint is not None and "mode" in self._fields:
            self.paste_hint.setVisible(self._fields["mode"][1].currentData() != "type")

    def _shortcut_chosen(self) -> None:
        picked = self.shortcut_picker.shortcut() if self.shortcut_picker else None
        if picked is None or self.is_loading:
            return
        component, name = picked
        with self.loading():
            self._fields["component"][1].set_value(component)
            self._fields["name"][1].set_value(name)
        self.changed.emit()
