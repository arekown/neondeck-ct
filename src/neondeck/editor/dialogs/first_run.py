"""Ersteinrichtung beim ersten Editor-Start: Diagnose → Vorlagen ankreuzen → Theme waehlen.

„Fertig“ fuegt die angekreuzten Vorlagen als Arbeitsbereiche ins aktive Profil ein
(``insert_templates`` des Fensters, mit Rückgängig und Version); nichts angekreuzt: das
Profil bleibt, wie es ist. Fertig wie Abbrechen setzen ``first_run_done``
(der Assistent kommt nie ungefragt wieder; im Menue „Extras“ laesst er sich erneut oeffnen).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import N_, tr
from ...ui import theme
from ...ui.common import Request
from ..windows.diagnose_page import DiagnosePage
from .template_picker import TemplateChooser

log = logging.getLogger(__name__)

WIZARD_SIZE = (820, 640)


class _DiagnoseStep(QWidget):
    title = N_("Einrichtung prüfen")

    def __init__(self, request: Request | None) -> None:
        super().__init__()
        self.page = DiagnosePage(request)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.page)


class _TemplateStep(QWidget):
    title = N_("Wofür nutzt du den CT?")

    def __init__(self) -> None:
        super().__init__()
        self.chooser = TemplateChooser()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.chooser)

    def chosen(self) -> list[str]:
        return self.chooser.chosen()

    def choose(self, template_ids) -> None:
        self.chooser.choose(template_ids)


class _ThemeStep(QWidget):
    title = N_("Aussehen wählen")

    def __init__(self, on_theme: Callable[[str], None]) -> None:
        super().__init__()
        self.group = QButtonGroup(self)
        layout = QVBoxLayout(self)
        self._names: list[str] = []
        for t in theme.THEMES.values():
            button = QRadioButton(tr(t.label))
            button.setChecked(t.name == theme.current().name)
            self.group.addButton(button, len(self._names))
            self._names.append(t.name)
            layout.addWidget(button)
        layout.addStretch(1)
        self._on_theme = on_theme
        self.group.idClicked.connect(lambda i: on_theme(self._names[i]))

    def choice(self) -> str:
        i = self.group.checkedId()
        return self._names[i] if 0 <= i < len(self._names) else theme.current().name

    def choose(self, name: str) -> None:
        """Wie ein Klick: waehlen und sofort anwenden."""
        if name in self._names:
            self.group.button(self._names.index(name)).setChecked(True)
            self._on_theme(name)


class FirstRunWizard(QDialog):
    """``request`` ist die API des Dienstes (Diagnose, ``first_run_done``); ``on_theme(name)``
    wendet ein Theme an, ``insert_templates(ids)`` fuegt Vorlagen ins aktive Profil ein,
    ``say(text)`` meldet in der Statuszeile des Fensters.

    Bewusst kein ``QWizard``: ein QWizard mit Seiten stuerzte (Speicherzugriffsfehler in
    QtWidgets) ab, wenn waehrend einer verschachtelten Ereignisschleife das App-Stylesheet
    wechselte – genau das passiert beim Theme-Wechsel mit anschliessendem Profilwechsel."""

    def __init__(self, request: Request | None, on_theme: Callable[[str], None],
                 insert_templates: Callable[[list[str]], list], say: Callable[[str], None],
                 parent=None) -> None:
        super().__init__(parent)
        self._request = request
        self._insert_templates = insert_templates
        self._say = say
        self._checked = False
        self.inserted: list = []  # templates.Inserted je eingefuegtem Arbeitsbereich
        self.setWindowTitle(tr("Neondeck CT – Ersteinrichtung"))
        self.resize(*WIZARD_SIZE)
        self.diagnose = _DiagnoseStep(request)
        self.templates = _TemplateStep()
        self.themes = _ThemeStep(on_theme)
        self.steps = [self.diagnose, self.templates, self.themes]
        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.stack = QStackedWidget()
        for step in self.steps:
            self.stack.addWidget(step)
        self.skip_button = QPushButton(tr("Überspringen"))
        self.back_button = QPushButton(tr("Zurück"))
        self.next_button = QPushButton(tr("Weiter"))
        self.finish_button = QPushButton(tr("Fertig"))
        self.skip_button.clicked.connect(self.reject)
        self.back_button.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next_button.clicked.connect(lambda: self.go(self.stack.currentIndex() + 1))
        self.finish_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        for b in (self.back_button, self.next_button, self.finish_button):
            buttons.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(self.heading)
        layout.addWidget(self.stack, 1)
        layout.addLayout(buttons)
        self.go(0)

    def go(self, index: int) -> None:
        index = max(0, min(len(self.steps) - 1, index))
        self.stack.setCurrentIndex(index)
        self.heading.setText(tr("Schritt {n} von {total}: {title}", n=index + 1,
                                total=len(self.steps), title=tr(self.steps[index].title)))
        self.back_button.setEnabled(index > 0)
        self.next_button.setVisible(index < len(self.steps) - 1)
        self.finish_button.setVisible(index == len(self.steps) - 1)
        self.finish_button.setDefault(index == len(self.steps) - 1)
        self.next_button.setDefault(index < len(self.steps) - 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._checked:  # Diagnose einmal beim ersten Zeigen
            self._checked = True
            self.diagnose.page.refresh()

    def done(self, result: int) -> None:
        """Erst schliessen, dann uebernehmen (Theme und Profilwechsel nie mitten im
        Schliessen des Dialogs)."""
        super().done(result)
        if getattr(result, "value", result) == QDialog.DialogCode.Accepted.value:
            try:
                self.apply()
            except Exception as e:
                log.exception("Ersteinrichtung nicht übernommen")
                self._say(tr("Ersteinrichtung: {error}", error=e))
        self._mark_done()

    def apply(self) -> None:
        """Angekreuzte Vorlagen ins aktive Profil einfuegen (das Theme gilt schon seit dem
        Klick auf der dritten Seite)."""
        chosen = self.templates.chosen()
        if chosen:
            self.inserted = self._insert_templates(chosen)

    def _mark_done(self) -> None:
        if self._request is None:
            return
        try:
            self._request("settings.put", {"first_run_done": True})
        except Exception as e:  # noqa: BLE001 - beim naechsten Start eben noch einmal
            log.warning("Ersteinrichtung nicht als erledigt gemerkt: %s", e)
