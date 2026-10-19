"""Kopfzeile des Einstellungsfensters: Profil- und Arbeitsbereichsauswahl, „Anordnen …“,
LED-Farbe, Leistenanzeige, „Vorlage einfügen …“ und der Schalter „Simulieren“.

Die Auswahlfelder melden nur Benutzerwahl (``profile_chosen``, ``workspace_chosen``); was das
Fenster selbst eintraegt, geht ohne Signal. Die Knoepfe und Menueeintraege verbindet das
Fenster mit seinen Controllern.
"""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QComboBox, QLabel, QMenu, QToolBar, QToolButton, QWidget

from ...core.i18n import N_, tr
from ...profile.model import (
    STRIP_KNOBS,
    STRIP_LEFT,
    STRIP_RIGHT,
    STRIP_SYSTEM,
    Profile,
    Workspace,
)
from ..widgets.base import menu_action
from ..widgets.color_button import DEFAULT_COLOR, color_icon

STRIP_SIDES = ((STRIP_LEFT, N_("Linke Leiste")), (STRIP_RIGHT, N_("Rechte Leiste")))
STRIP_MODE_LABELS = ((STRIP_KNOBS, N_("Regler")),
                     (STRIP_SYSTEM, N_("Systemlast (CPU, RAM, GPU)")))
LABEL_MARGINS = (6, 0, 4, 0)


def _label(text: str, buddy: QWidget) -> QLabel:
    label = QLabel(text)
    label.setBuddy(buddy)
    label.setContentsMargins(*LABEL_MARGINS)
    return label


def _button(text: str, tip: str, icon: str | None = None) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    if icon:
        b.setIcon(QIcon.fromTheme(icon))
    b.setToolTip(tip)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    return b


def _combo() -> QComboBox:
    c = QComboBox()
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    return c


class ProfileToolbar(QToolBar):
    profile_chosen = Signal(str)
    workspace_chosen = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(tr("Profil"), parent)
        self.setObjectName("profile-toolbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.profile_combo = _combo()
        self.profile_combo.currentIndexChanged.connect(
            lambda i: self.profile_chosen.emit(self.profile_combo.itemData(i) or ""))
        self.workspace_combo = _combo()
        self.workspace_combo.currentIndexChanged.connect(
            lambda i: self.workspace_chosen.emit(self.workspace_combo.itemData(i) or ""))
        self.addWidget(_label(tr("Profil:"), self.profile_combo))
        self.addWidget(self.profile_combo)
        self.addSeparator()
        self.addWidget(_label(tr("Arbeitsbereich:"), self.workspace_combo))
        self.addWidget(self.workspace_combo)
        self.arrange_button = _button(tr("Anordnen …"),
                                      tr("Arbeitsbereiche und Seiten per Ziehen sortieren"),
                                      "view-sort")
        self.addWidget(self.arrange_button)
        self._build_led()
        self._build_strips()
        self.template_button = _button(tr("Vorlage einfügen …"),
                                       tr("Vorlagen (Medien, Entwickler, Grafik, Gaming …) als "
                                          "eigene Arbeitsbereiche in dieses Profil einfügen"),
                                       "list-add")
        self.addWidget(self.template_button)
        self.addSeparator()

    def _build_led(self) -> None:
        self.led_button = _button(tr("LED-Farbe"), tr("Farbe, in der die runde Taste dieses "
                                            "Arbeitsbereichs leuchtet"))
        self.led_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.led_menu = QMenu(self.led_button)
        self.led_choose_action = menu_action(self.led_menu, "color-picker", tr("Farbe wählen …"))
        self.led_reset_action = menu_action(self.led_menu, None, tr("Standard (weiß)"))
        self.led_button.setMenu(self.led_menu)
        self.addWidget(self.led_button)

    def _build_strips(self) -> None:
        self.strips_button = _button(tr("Leisten"), tr("Was die Seitenleisten dieses Arbeitsbereichs "
                                               "zeigen: die Regler oder die Systemlast (CPU, "
                                               "RAM, GPU 1, GPU 2)"))
        self.strips_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.strips_menu = QMenu(self.strips_button)
        self.strip_actions: dict[tuple[str, str], QAction] = {}
        for side, side_label in STRIP_SIDES:
            if side != STRIP_SIDES[0][0]:
                self.strips_menu.addSeparator()
            group = QActionGroup(self.strips_menu)  # je Leiste genau eine Anzeige
            for mode, mode_label in STRIP_MODE_LABELS:
                action = menu_action(self.strips_menu, None, tr("{side}: {mode}", side=tr(side_label),
                                                         mode=tr(mode_label)))
                action.setCheckable(True)
                group.addAction(action)
                self.strip_actions[(side, mode)] = action
        self.strips_button.setMenu(self.strips_menu)
        self.addWidget(self.strips_button)

    # --- Anzeige ---------------------------------------------------------------------------

    def set_profiles(self, entries: list[tuple[str, str]], current: str) -> None:
        """Profilauswahl ``(Kennung, Name)``; ``current`` gewaehlt (ohne Signal)."""
        with QSignalBlocker(self.profile_combo):
            self.profile_combo.clear()
            for pid, name in entries:
                self.profile_combo.addItem(name, pid)
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(current))

    def profile_entries(self) -> list[tuple[str, str]]:
        combo = self.profile_combo
        return [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())]

    def profile_name(self, pid: str) -> str:
        i = self.profile_combo.findData(pid)
        return self.profile_combo.itemText(i) if i >= 0 else pid

    def show_workspace(self, profile: Profile, ws_id: str | None,
                       ws: Workspace | None) -> None:
        """Arbeitsbereiche von ``profile`` (``ws_id`` gewaehlt, ohne Signal); LED-Farbe und
        Leistenanzeige von ``ws``."""
        with QSignalBlocker(self.workspace_combo):
            self.workspace_combo.clear()
            for w in profile.workspaces:
                self.workspace_combo.addItem(w.name or w.id, w.id)
            self.workspace_combo.setCurrentIndex(self.workspace_combo.findData(ws_id))
        self.led_button.setEnabled(ws is not None)
        self.led_button.setIcon(color_icon((ws.led_color if ws else None) or DEFAULT_COLOR))
        self.strips_button.setEnabled(ws is not None)
        for (side, mode), action in self.strip_actions.items():
            action.setChecked(ws is not None and ws.strip_mode(side) == mode)
