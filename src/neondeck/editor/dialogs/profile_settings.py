"""Profil-Einstellungen: Anwendungen fuer den Dynamic Mode, automatisch aktivieren, halten."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ...core.i18n import N_, tr
from ...profile.model import Profile
from ..widgets.base import tool_button
from ..widgets.param_widgets import AppPicker, Catalog

APPS_HINT = N_("Wird eine dieser Anwendungen aktiv, wechselt das Gerät auf dieses Profil "
               "(Desktop-ID oder Fensterklasse).")


class ProfileSettingsDialog(QDialog):
    """Bearbeitet ``app_ids``, ``dynamic`` und ``hold_profile`` einer Kopie; ``apply(profile)``
    uebertraegt die Werte."""

    def __init__(self, profile: Profile, catalog: Catalog | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Profil-Einstellungen – {name}", name=profile.name or profile.id))
        self.apps = QListWidget()
        for app_id in profile.app_ids:
            self.apps.addItem(QListWidgetItem(app_id))
        self.picker = AppPicker(catalog)
        self.add_button = tool_button("list-add", "+", tr("Anwendung hinzufügen"), self._add)
        self.remove_button = tool_button("list-remove", "−", tr("Anwendung entfernen"), self._remove)
        row = QHBoxLayout()
        row.addWidget(self.picker, 1)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        hint = QLabel(tr(APPS_HINT))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.dynamic_check = QCheckBox(tr("Automatisch aktivieren, wenn eine Anwendung aktiv wird"))
        self.dynamic_check.setChecked(profile.dynamic)
        self.hold_check = QCheckBox(tr("Halten: ohne passende Anwendung nicht zum Standardprofil "
                                       "zurückwechseln"))
        self.hold_check.setChecked(profile.hold_profile)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow(tr("Anwendungen:"), self.apps)
        form.addRow("", row)
        form.addRow(hint)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.dynamic_check)
        layout.addWidget(self.hold_check)
        layout.addWidget(buttons)
        self.apps.currentRowChanged.connect(lambda _r: self._update())
        self._update()

    def app_ids(self) -> list[str]:
        return [self.apps.item(i).text() for i in range(self.apps.count())]

    def _add(self) -> None:
        app_id = str(self.picker.value() or "").strip()
        if app_id and app_id not in self.app_ids():
            self.apps.addItem(QListWidgetItem(app_id))
        self.picker.set_value("")
        self._update()

    def _remove(self) -> None:
        row = self.apps.currentRow()
        if row >= 0:
            self.apps.takeItem(row)
        self._update()

    def _update(self) -> None:
        self.remove_button.setEnabled(self.apps.currentRow() >= 0)

    def apply(self, profile: Profile) -> bool:
        """Werte ins Profil; ``True``, wenn sich etwas geaendert hat."""
        new = (self.app_ids(), self.dynamic_check.isChecked(), self.hold_check.isChecked())
        if new == (profile.app_ids, profile.dynamic, profile.hold_profile):
            return False
        profile.app_ids, profile.dynamic, profile.hold_profile = new
        if profile.app and profile.app not in profile.app_ids:
            profile.app = None  # altes Einzelfeld (v1) nicht wieder auferstehen lassen
        return True
