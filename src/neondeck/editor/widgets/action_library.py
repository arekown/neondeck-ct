"""Aktionsliste: alle Aktionstypen nach Kategorie, durchsuchbar, aufs Geraet ziehbar.

Ein Eintrag ist eine Vorlage (Typ mit Standardparametern). Ziehen legt sie auf ein
Element der Geraeteansicht (MIME ``ACTION_MIME``), Doppelklick wendet sie auf das
gewaehlte Element an (Signal ``activated``).
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ...actions.base import ActionType, registry
from ...core.i18n import N_, tr
from ...engine.kinds import LIVE_TYPES
from ..editing.mime import ACTION_MIME, put_json
from .action_meta import HIDDEN_TYPES, category_name, ordered_categories

TYPE_ROLE = Qt.ItemDataRole.UserRole
CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1

# Weitere Suchbegriffe, wenn die Bezeichnung das gesuchte Wort nicht enthaelt
KEYWORDS = {
    "run": N_("Anwendung App Programm öffnen"),
    "open": N_("Datei Ordner URL Webseite Link Browser"),
    "command": N_("Konsole Terminal Shell Skript Kommando"),
    "hotkey": N_("Tastenkombination Shortcut Tastatur Kürzel"),
    "hold_key": N_("gedrückt halten Tastatur Umschalt Strg"),
    "text": N_("tippen einfügen schreiben Zwischenablage"),
    "adjust_hotkey": N_("Regler drehen Tastatur Kürzel"),
    "volume": N_("Ton Audio Sound lauter leiser"),
    "mute_toggle": N_("Ton Audio Sound stumm"),
    "media": N_("Wiedergabe Pause Musik Titel Play Wiederholen Loop"),
    "brightness": N_("Bildschirm Monitor heller dunkler"),
    "brightness_reset": N_("Bildschirm Monitor"),
    "kde": N_("Plasma KWin Fenster Desktop Übersicht"),
    "kde_adjust": N_("Plasma KWin Fenster Desktop wechseln Regler"),
    "open_config": N_("Einstellungen"),
    "clock": N_("Zeit Uhrzeit"),
    "date": N_("Kalender Kalenderwoche"),
    "stopwatch": N_("Timer Zeit messen"),
    "macro": N_("Abfolge Schritte Ablauf"),
    "sleep": N_("Pause Verzögerung warten"),
    "adjust_macro": N_("Regler Schritte drehen"),
    "http": N_("Webhook Web URL Anfrage REST Netzwerk"),
    "app_focus": N_("Anwendung App Programm Fenster wechseln starten"),
    "mic_mute": N_("Mikrofon Ton Audio Eingang stumm"),
    "audio_output_next": N_("Ton Audio Lautsprecher Kopfhörer Ausgang Gerät"),
    "kde_shortcut": N_("Plasma KWin Tastenkürzel Kurzbefehl global"),
    "dynamic_folder": N_("Fenster Umschalter Mixer Anwendungen Taskleiste"),
    "scroll": N_("Mausrad Zoom Regler drehen blättern"),
    "terminal_layout": N_("Terminal Shell ssh geteilt Fenster platzieren Bildschirm"),
}
DRAG_HINT = N_("Auf ein Element am Gerät ziehen oder doppelklicken")


def template(at: ActionType) -> dict:
    """Neue Aktion dieses Typs mit den Standardwerten seiner Parameter."""
    action: dict = {"type": at.name}
    for p in at.params:
        if p.default is not None:
            action[p.name] = p.default
    return action


def _usage(at: ActionType) -> str:
    if at.name in LIVE_TYPES:
        return tr("Anzeige – nur auf Touch-Tasten")
    if at.kinds == {"rotate"}:
        return tr("Drehaktion – für Regler und Rad")
    if "rotate" in at.kinds:
        return tr("Für Regler (Drehen und Drücken)")
    return tr("Für Tasten und Reglerdruck")


class _Tree(QTreeWidget):
    """Baum, dessen Eintraege ihre Vorlage als ``ACTION_MIME`` mitgeben.

    Gezogen wird nur kopierend: der Standard-``startDrag`` wuerde einen Eintrag nach
    einem „Verschieben“ (Umschalt beim Ablegen) aus der Liste entfernen.
    """

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction

    def startDrag(self, _actions) -> None:
        mime = self.mimeData(self.selectedItems())
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)

    def mimeTypes(self) -> list[str]:
        return [ACTION_MIME]

    def mimeData(self, items) -> QMimeData | None:
        at = next((registry().get(i.data(0, TYPE_ROLE)) for i in items
                   if i.data(0, TYPE_ROLE)), None)
        if at is None:
            return None
        return put_json(QMimeData(), ACTION_MIME, template(at))


class ActionLibrary(QWidget):
    activated = Signal(dict)  # Vorlage per Doppelklick/Eingabetaste

    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Aktion suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.tree.itemActivated.connect(self._activate)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        self._fill()

    def _fill(self) -> None:
        by_cat: dict[str, list[ActionType]] = {}
        for at in registry().values():
            if at.name not in HIDDEN_TYPES:
                by_cat.setdefault(at.category, []).append(at)
        for cat in ordered_categories(by_cat):
            head = QTreeWidgetItem([category_name(cat)])
            head.setData(0, CATEGORY_ROLE, cat)
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(head)
            for at in by_cat[cat]:
                item = QTreeWidgetItem(head, [tr(at.label)])
                item.setData(0, TYPE_ROLE, at.name)
                item.setToolTip(0, f"{_usage(at)}\n{tr(DRAG_HINT)}")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                              | Qt.ItemFlag.ItemIsDragEnabled)
        self.tree.expandAll()

    # Eintraege werden jedes Mal im Baum nachgeschlagen, nie aufgehoben (Lektion
    # L-2026-10-18-03: der Baum besitzt sie in C++).

    def _heads(self) -> list[tuple[str, QTreeWidgetItem]]:
        """``(Kategorie-Schluessel, Ueberschrift)`` in Anzeigereihenfolge."""
        heads = (self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()))
        return [(head.data(0, CATEGORY_ROLE), head) for head in heads]

    def _type_items(self) -> list[tuple[str, QTreeWidgetItem]]:
        return [(head.child(i).data(0, TYPE_ROLE), head.child(i))
                for _cat, head in self._heads() for i in range(head.childCount())]

    @staticmethod
    def _haystack(item: QTreeWidgetItem, category: str) -> str:
        name = item.data(0, TYPE_ROLE)
        return " ".join((item.text(0), category_name(category),
                         tr(KEYWORDS.get(name, "")))).casefold()

    def _filter(self, text: str) -> None:
        words = text.casefold().split()
        for cat, head in self._heads():
            shown = 0
            for i in range(head.childCount()):
                child = head.child(i)
                hay = self._haystack(child, cat)
                hidden = not all(w in hay for w in words)
                child.setHidden(hidden)
                shown += not hidden
            head.setHidden(shown == 0)
        self.tree.expandAll()

    def _activate(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        at = registry().get(item.data(0, TYPE_ROLE) or "")
        if at is not None:
            self.activated.emit(template(at))

    # --- Abfragen (Tests, Fenster) -----------------------------------------------------

    def category_names(self) -> list[str]:
        """Kategorie-Schluessel in Anzeigereihenfolge."""
        return [cat for cat, _head in self._heads()]

    def visible_categories(self) -> list[str]:
        return [cat for cat, head in self._heads() if not head.isHidden()]

    def visible_types(self) -> list[str]:
        return [name for name, item in self._type_items()
                if not item.isHidden() and not item.parent().isHidden()]

    def item(self, type_name: str) -> QTreeWidgetItem:
        return next(item for name, item in self._type_items() if name == type_name)

    def category_item(self, name: str) -> QTreeWidgetItem:
        return next(head for cat, head in self._heads() if cat == name)

    def mime_data(self, type_name: str) -> QMimeData | None:
        return self.tree.mimeData([self.item(type_name)])
