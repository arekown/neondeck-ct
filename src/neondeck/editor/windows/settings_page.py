"""Editor-Seite „Einstellungen“: Programmeinstellungen des Dienstes (API ``settings.put``).

Jede Aenderung geht sofort an den Dienst, der sie anwendet und speichert (Sprache, Dynamic Mode,
Bildschirmsperre, Geraete-Look, Display-Schlaf, Bildschirmschoner, Schwellen fuer Doppeltippen/Halten, Tray-Symbol,
Benachrichtigungen je Art). Lehnt der Dienst ab, zeigt die Seite den Grund und laedt den
gespeicherten Stand neu.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import i18n
from ...core.i18n import N_, tr
from ...core.settings import FIELDS
from ...core.values import is_int
from ...render.savers import SAVERS
from ...ui.common import Request
from ..widgets.base import EditorWidget, combo, hbox, hint_label

log = logging.getLogger(__name__)


# Schluessel -> Beschriftung (Ein/Aus); Tabellen markieren mit N_, angezeigt wird tr(text)
DEVICE_FLAGS = {
    "dynamic_mode": N_("Dynamic Mode: Profil folgt dem aktiven Fenster"),
    "lock_with_session": N_("Bildschirmsperre sperrt auch das Gerät"),
}
QUIET_FLAGS = {
    "tray_mono": N_("Einfarbiges Tray-Symbol"),
    "notify_errors": N_("Meldung bei Fehlern"),
    "notify_connection": N_("Meldung, wenn das Gerät getrennt oder wieder verbunden wird"),
    "notify_profile": N_("Meldung bei Profilwechsel"),
}
# Geraete-Look (settings.LOOK_NAMES) -> Eintrag in der Auswahl
LOOK_LABELS = {
    "auto": N_("Passend zum Theme"),
    "classic": N_("Klassisch"),
    "cockpit": N_("Cockpit (animiert)"),
}
# Schluessel -> (Beschriftung, Bereich, Einheit, Text fuer 0)
# (Bereiche aus dem Settings-Schema, damit Seite und Dienst dasselbe erlauben)
NUMBERS = {
    "display_sleep_min": (N_("Displays schlafen nach"), FIELDS["display_sleep_min"].valid,
                          N_(" min"), N_("nie")),
    "screensaver_min": (N_("Bildschirmschoner nach"), FIELDS["screensaver_min"].valid,
                        N_(" min"), N_("aus")),
    "screensaver_slide_s": (N_("Diashow: Bild wechselt alle"),
                            FIELDS["screensaver_slide_s"].valid, N_(" s"), None),
    "double_ms": (N_("Doppeltippen innerhalb von"), FIELDS["double_ms"].valid, N_(" ms"), None),
    "hold_ms": (N_("Halten ab"), FIELDS["hold_ms"].valid, N_(" ms"), None),
}


SAVER_HINT = N_("Die erste Berührung am Gerät beendet den Bildschirmschoner, ohne die Aktion "
                "dahinter auszulösen. Schlafen die Displays früher, gewinnt der Schlaf.")


class SettingsPage(EditorWidget, QWidget):
    def __init__(self, request: Request, parent=None) -> None:
        super().__init__(parent)
        self._request = request
        self.checks: dict[str, QCheckBox] = {}
        self.spins: dict[str, QSpinBox] = {}
        self.combos: dict[str, QComboBox] = {}  # Schluessel -> Auswahl (Standard „auto“)
        heading = QLabel(tr("Einstellungen"))
        heading.setObjectName("heading")
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        quiet = QGroupBox(tr("Ruhe: Tray und Benachrichtigungen"))
        quiet_layout = QVBoxLayout(quiet)
        for key, text in QUIET_FLAGS.items():
            quiet_layout.addWidget(self._check(key, tr(text)))
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.error)
        layout.addWidget(self._build_language())
        layout.addWidget(self._build_device())
        layout.addWidget(quiet)
        layout.addStretch(1)

    def _build_language(self) -> QGroupBox:
        """Gruppe „Sprache“: Systemsprache oder eine der Sprachdateien (``data/i18n``)."""
        group = QGroupBox(tr("Sprache"))
        form = QFormLayout(group)
        self.language_combo = self._combo(
            "language", [(i18n.AUTO, tr("Systemsprache"))] + i18n.available())
        form.addRow(tr("Sprache:"), self.language_combo)
        form.addRow(hint_label(tr("Wirkt nach Neustart von Editor und Dienst.")))
        return group

    def _build_device(self) -> QGroupBox:
        """Gruppe „Gerät“: Schalter, Geräte-Look, Zeiten, Bildschirmschoner, Diashow-Ordner."""
        device = QGroupBox(tr("Gerät"))
        form = QFormLayout(device)
        for key, text in DEVICE_FLAGS.items():
            form.addRow(self._check(key, tr(text)))
        self.look_combo = self._combo("device_look", [(n, tr(LOOK_LABELS.get(n, n)))
                                                      for n in FIELDS["device_look"].valid])
        self.look_combo.setToolTip(tr("Aussehen der Displays am Gerät; „Cockpit“ animiert "
                                      "Raster, Rahmen, Leisten, Rad und LEDs – die Tasten "
                                      "bleiben dabei bedienbar"))
        form.addRow(tr("Geräte-Look:"), self.look_combo)
        for key, (text, valid, unit, zero) in NUMBERS.items():
            form.addRow(tr("{label}:", label=tr(text)),
                         self._spin(key, valid, tr(unit), tr(zero) if zero else zero))
        self.saver_combo = self._combo("screensaver", [("auto", tr("Passend zum Theme"))]
                                       + [(n, tr(cls.label)) for n, cls in SAVERS.items()])
        self.preview_button = QPushButton(tr("Vorschau am Gerät"))
        self.preview_button.setToolTip(tr("Startet den Bildschirmschoner sofort; eine Berührung "
                                          "am Gerät beendet ihn"))
        self.preview_button.clicked.connect(self.preview)
        form.addRow(tr("Bildschirmschoner:"), hbox((self.saver_combo, 1), self.preview_button))
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText(tr("kein Ordner gewählt"))
        self.folder_button = QPushButton(tr("Ordner wählen …"))
        self.folder_button.setToolTip(tr("Bilder aus diesem Ordner (samt Unterordnern) als "
                                         "Diashow; stellt den Bildschirmschoner auf „Diashow“"))
        self.folder_button.clicked.connect(self.choose_folder)
        form.addRow(tr("Diashow-Ordner:"), hbox((self.folder_edit, 1), self.folder_button))
        form.addRow(hint_label(tr(SAVER_HINT)))
        return device

    def _check(self, key: str, text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.toggled.connect(lambda on, k=key: self._put(k, on))
        self.checks[key] = box
        return box

    def _spin(self, key: str, valid: range, unit: str, zero: str | None) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(valid.start, valid.stop - 1)
        spin.setSuffix(unit)
        spin.setKeyboardTracking(False)  # erst nach der Eingabe senden
        if zero:
            spin.setSpecialValueText(zero)
        spin.valueChanged.connect(lambda v, k=key: self._put(k, v))
        self.spins[key] = spin
        return spin

    def _combo(self, key: str, choices) -> QComboBox:
        box = combo(choices)
        box.currentIndexChanged.connect(lambda _i, k=key, b=box: self._put(k, b.currentData()))
        self.combos[key] = box
        return box

    def load(self, values: dict | None = None) -> bool:
        """Stand vom Dienst holen (oder ``values``) und anzeigen; ``False`` ohne Dienst."""
        if values is None:
            try:
                values = self._request("settings.get", {})
            except Exception as e:  # noqa: BLE001 - Dienst weg
                self._show_error(tr("Einstellungen nicht geladen: {error}", error=e))
                return False
        if not isinstance(values, dict):
            return False
        with self.loading():
            for key, box in self.checks.items():
                box.setChecked(bool(values.get(key, box.isChecked())))
            for key, spin in self.spins.items():
                v = values.get(key)
                if is_int(v):
                    spin.setValue(v)
            for key, box in self.combos.items():
                box.setCurrentIndex(max(0, box.findData(values.get(key, "auto"))))
            self.folder_edit.setText(str(values.get("screensaver_folder") or ""))
        return True

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Bilderordner für die Diashow"),
                                                  self.folder_edit.text() or None)
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder: str) -> None:
        """Ordner merken und die Diashow als Bildschirmschoner waehlen."""
        self._put_many({"screensaver_folder": folder, "screensaver": "diashow"})

    def _put(self, key: str, value) -> None:
        self._put_many({key: value})

    def _put_many(self, values: dict) -> None:
        if self.is_loading:
            return
        try:
            result = self._request("settings.put", values)
        except Exception as e:  # noqa: BLE001 - abgelehnt oder Dienst weg
            log.warning("Einstellung %s nicht gespeichert: %s", ", ".join(values), e)
            self._show_error(tr("„{keys}“ nicht gespeichert: {error}", keys=", ".join(values),
                                    error=e))
            self.load()
            return
        self.error.hide()
        self.load(result if isinstance(result, dict) else None)

    def preview(self) -> None:
        try:
            self._request("screensaver.start", {"name": self.saver_combo.currentData()})
        except Exception as e:  # noqa: BLE001 - gesperrt, schlaeft oder Dienst weg
            self._show_error(tr("Vorschau nicht gestartet: {error}", error=e))
            return
        self.error.hide()

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()
