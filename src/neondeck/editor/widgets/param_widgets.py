"""Eingaben im Aktionsformular, alle mit ``value``/``set_value``/``changed``
(``param_factory.ParamWidget``): Ja/Nein, Zahl, Auswahl, Textzeile, Datei/Ordner, mehrzeiliger
Text, Konsole-Fensterliste, Anwendungs- und Kürzelauswahl.

Die Listen der Anwendungen (``apps.list``) und KDE-Kürzel (``kde.shortcuts``) kommen vom
Dienst (``Catalog``): einmal im Hintergrund geholt, sobald ein Auswahlfeld sichtbar wird; die
Felder fuellen sich, wenn die Antwort da ist. Alle Auswahlfelder bleiben editierbar – was nicht in der Liste steht, kann
eingetippt werden.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ...actions.terminal_windows import windows_from_text, windows_to_text
from ...core.i18n import N_, tr
from .base import EditorWidget

log = logging.getLogger(__name__)

APPS = "apps.list"
SHORTCUTS = "kde.shortcuts"
Fetch = Callable[[str, dict, Callable], None]  # (Methode, Parameter, Rueckruf(result, error))
INT_RANGE = (0, 100000)
MULTILINE_PAD_PX = 14  # Rand und Rahmen eines mehrzeiligen Felds


class Catalog(QObject):
    """Anwendungen und KDE-Kürzel vom Dienst (``fetch`` = ``RemoteEngine.request_async``)."""

    changed = Signal()

    def __init__(self, fetch: Fetch | None = None, parent=None) -> None:
        super().__init__(parent)
        self._fetch = fetch
        self._data: dict[str, list | None] = {APPS: None, SHORTCUTS: None}
        self._asked: set[str] = set()

    def apps(self, fetch: bool = True) -> list[dict]:
        """``[{"id", "name", "icon", …}]`` (leer, solange die Antwort fehlt); ``fetch``:
        beim Dienst anfragen, wenn noch nicht geschehen."""
        return self._get(APPS, fetch)

    def shortcuts(self, fetch: bool = True) -> list[dict]:
        """``[{"component", "name", "friendly"}]``."""
        return self._get(SHORTCUTS, fetch)

    def set(self, method: str, data: list) -> None:
        self._data[method] = list(data)
        self.changed.emit()

    def _get(self, method: str, fetch: bool = True) -> list:
        if fetch and self._data[method] is None and method not in self._asked and self._fetch:
            self._asked.add(method)
            try:
                self._fetch(method, {}, lambda r, e, m=method: self._got(m, r, e))
            except Exception as e:  # noqa: BLE001 - Liste fehlt dann nur
                log.warning("%s nicht abfragbar: %s", method, e)
                self._asked.discard(method)
        return list(self._data[method] or [])

    def _got(self, method: str, result, error) -> None:
        if error is None and isinstance(result, list):
            self.set(method, [x for x in result if isinstance(x, dict)])
        else:
            log.info("%s nicht geladen: %s", method, error)
            self._asked.discard(method)  # beim naechsten Oeffnen neu versuchen


# --- Einfache Eingaben ------------------------------------------------------------------

class CheckParam(QCheckBox):
    """Ja/Nein."""

    changed = Signal()

    def __init__(self, default=None, parent=None) -> None:
        super().__init__(parent)
        self.setChecked(bool(default))
        self.toggled.connect(self.changed)

    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, v) -> None:
        self.setChecked(bool(v))


class SpinParam(QSpinBox):
    """Ganze Zahl (``value`` ist die von QSpinBox)."""

    changed = Signal()

    def __init__(self, default=None, parent=None) -> None:
        super().__init__(parent)
        self.setRange(*INT_RANGE)
        self.setValue(int(default or 0))
        self.valueChanged.connect(self.changed)

    def set_value(self, v) -> None:
        with contextlib.suppress(TypeError, ValueError):
            self.setValue(int(v))


class ChoiceParam(QComboBox):
    """Auswahl aus ``(Wert, Beschriftung)``; ein Wert ausserhalb der Auswahl wird angezeigt
    statt verworfen."""

    changed = Signal()

    def __init__(self, choices: Iterable[tuple[object, str]], default=None,
                 parent=None) -> None:
        super().__init__(parent)
        for value, label in choices:
            self.addItem(label, value)
        self.setCurrentIndex(max(0, self.findData(default)))
        self.currentIndexChanged.connect(self.changed)

    def value(self):
        return self.currentData()

    def set_value(self, v) -> None:
        i = self.findData(v)
        if i < 0:
            self.addItem(str(v), v)
            i = self.count() - 1
        self.setCurrentIndex(i)


class LineParam(QLineEdit):
    """Einzeiliger Text."""

    changed = Signal()

    def __init__(self, default=None, parent=None) -> None:
        super().__init__(parent)
        if default:
            self.setText(str(default))
        self.textChanged.connect(self.changed)

    def value(self) -> str:
        return self.text()

    def set_value(self, v) -> None:
        self.setText("" if v is None else str(v))


class PathEdit(QWidget):
    """Zeile + „Durchsuchen …“ fuer Datei- oder Ordnerparameter."""

    changed = Signal()

    def __init__(self, directory: bool, parent=None):
        super().__init__(parent)
        self._directory = directory
        self.line = QLineEdit()
        self.line.textChanged.connect(self.changed)
        icon = "document-open-folder" if directory else "document-open"
        browse = QPushButton(QIcon.fromTheme(icon), tr("Durchsuchen …"))
        browse.clicked.connect(self._browse)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.line, 1)
        row.addWidget(browse)

    def value(self) -> str:
        return self.line.text()

    def set_value(self, v) -> None:
        self.line.setText("" if v is None else str(v))

    def _browse(self) -> None:
        start = self.line.text() or str(Path.home())
        if self._directory:
            path = QFileDialog.getExistingDirectory(self, tr("Ordner wählen"), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, tr("Datei wählen"), start)
        if path:
            self.line.setText(path)


class MultiLineEdit(QPlainTextEdit):
    """Mehrzeiliger Text (z. B. HTTP-Kopfzeilen) mit ``value``/``set_value``/``changed``."""

    changed = Signal()

    def __init__(self, lines: int = 4, parent=None) -> None:
        super().__init__(parent)
        self.setTabChangesFocus(True)
        self.setFixedHeight(QFontMetrics(self.font()).lineSpacing() * lines
                            + MULTILINE_PAD_PX)
        self.textChanged.connect(self.changed)

    def value(self) -> str:
        return self.toPlainText()

    def set_value(self, v) -> None:
        self.setPlainText("" if v is None else str(v))


TERMINALS_HINT = N_("Je Fenster: Titel | Platz [| vertical] [| Bildschirm]\n"
                    "    darunter eingerückt je geteilte Ansicht ein Befehl (- = Shell)\n\n"
                    "Lokal | top_left\n    htop\n\nServer | top_right | vertical\n    -\n"
                    "    ssh 192.0.2.10\n\n"
                    "Register: Titel | Platz | tabs, darunter je Register Titel > Befehl\n\n"
                    "SSH | left | tabs\n    PC1\n    PC2 > ssh user@server1")


class TerminalsEdit(MultiLineEdit):
    """Fensterliste der Aktion „Konsole-Layout“ als Text (``actions.terminal_windows``);
    ``value`` ist die Liste der Fenster."""

    def __init__(self, parent=None) -> None:
        super().__init__(lines=8, parent=parent)
        self.setPlaceholderText(tr(TERMINALS_HINT))

    def value(self) -> list[dict]:
        return windows_from_text(self.toPlainText())

    def set_value(self, v) -> None:
        if v != self.value():  # beim Tippen nicht neu schreiben (Cursor bliebe nicht stehen)
            self.setPlainText(windows_to_text(v))


class _Picker(EditorWidget, QComboBox):
    """Editierbares Auswahlfeld; ``value`` = Daten des gewaehlten Eintrags oder der Text."""

    def __init__(self, catalog: Catalog | None, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
        self.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._catalog = catalog
        self.currentIndexChanged.connect(self._emit)
        self.editTextChanged.connect(self._emit)
        if catalog is not None:
            catalog.changed.connect(self.refill)
        self.refill()

    def entries(self) -> list[tuple[str, object, QIcon]]:
        raise NotImplementedError

    def load(self) -> None:
        """Liste beim Dienst anfragen (erst wenn das Feld sichtbar wird)."""
        raise NotImplementedError

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._catalog is not None:
            self.load()

    def refill(self) -> None:
        keep = self.value()
        with self.loading():
            self.clear()
            for text, data, icon in self.entries():
                self.addItem(icon, text, data)
            self._show(keep)

    def _show(self, v) -> None:
        i = self.findData(v) if v not in (None, "") else -1
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            self.setCurrentIndex(-1)
            self.setEditText(self._text_for(v))

    @staticmethod
    def _text_for(v) -> str:
        return "" if v is None else str(v)

    def value(self):
        text = self.currentText().strip()
        i = self.currentIndex()
        if i >= 0 and self.itemText(i) == self.currentText():
            return self.itemData(i)
        i = self.findText(text)
        return self.itemData(i) if i >= 0 else text

    def set_value(self, v) -> None:
        with self.loading():
            self._show(v)


def _app_icon(name: str) -> QIcon:
    if not name:
        return QIcon()
    if Path(name).is_absolute():
        return QIcon(name)
    return QIcon.fromTheme(name)


class AppPicker(_Picker):
    """Anwendung (Desktop-ID) aus ``apps.list``."""

    def load(self) -> None:
        self._catalog.apps()

    def entries(self):
        apps = self._catalog.apps(fetch=False) if self._catalog else []
        return [(f"{a.get('name') or a.get('id')} ({a.get('id')})", a.get("id"),
                 _app_icon(str(a.get("icon") or ""))) for a in apps if a.get("id")]


class ShortcutPicker(_Picker):
    """KDE-Kürzel aus ``kde.shortcuts``; ``value`` = ``(Komponente, Name)`` oder Text."""

    def load(self) -> None:
        self._catalog.shortcuts()

    def entries(self):
        items = self._catalog.shortcuts(fetch=False) if self._catalog else []
        out = []
        for s in items:
            comp, name = s.get("component"), s.get("name")
            if comp and name:
                out.append((f"{comp} › {s.get('friendly') or name}", f"{comp}\n{name}", QIcon()))
        return sorted(out, key=lambda e: e[0].casefold())

    def shortcut(self) -> tuple[str, str] | None:
        v = self.value()
        if isinstance(v, str) and "\n" in v:
            comp, name = v.split("\n", 1)
            return comp, name
        return None

    def set_shortcut(self, component: str, name: str) -> None:
        key = f"{component}\n{name}"
        self.set_value(key if self.findData(key) >= 0 else "")
