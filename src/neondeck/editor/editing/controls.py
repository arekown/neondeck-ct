"""Elemente bearbeiten (Menue „Bearbeiten“, Ziehen, Ablegen, Rechtsklick am Geraetebild):
Kopieren/Ausschneiden/Einfügen/Duplizieren/Löschen der gewaehlten Elemente, Ziehen zwischen
Elementen (verschieben, mit Strg kopieren), Aktionen aus der Bibliothek und Dateien aus dem
Dateimanager ablegen. Die Aenderung am Profil macht ``profile.edit``; hier stehen Meldungen,
Zwischenablage und Auswahl."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QKeySequenceEdit,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
)

from ...actions.base import registry
from ...core.i18n import N_, tr
from ...device.layout import ControlKind, ControlRef
from ...engine.kinds import LIVE_TYPES
from ...engine.painter import action_label
from ...profile import edit
from ..widgets.base import disposing, menu_action
from ..widgets.labels import ref_name
from . import clipboard
from .file_drop import assignment_for

if TYPE_CHECKING:
    from .host import EditView

FOLDER_LOCKED = N_("Feld 1 einer Ordnerseite ist immer „Zurück“ und lässt sich nicht belegen.")
TEXT_INPUTS = (QLineEdit, QPlainTextEdit, QAbstractSpinBox, QKeySequenceEdit)
REFUSALS = {
    edit.Refusal.TOUCH_ONLY: N_("Uhr, Datum und Stoppuhr gibt es nur auf Touch-Tasten"),
    edit.Refusal.LOCKED: FOLDER_LOCKED,
    edit.Refusal.ROTATE_ONLY: N_("Das Rad kann nur Drehaktionen ausführen"),
    edit.Refusal.PRESS_ONLY: N_("Tasten können keine Drehaktionen ausführen"),
}
FILE_KINDS = frozenset({ControlKind.TOUCH, ControlKind.SQUARE, ControlKind.ROUND})


def _typing() -> bool:
    """Steht der Fokus in einem Eingabefeld? (Strg+D gehoert dann dem Feld.)"""
    w = QApplication.focusWidget()
    return isinstance(w, TEXT_INPUTS) or (isinstance(w, QComboBox) and w.isEditable())


class ControlEditing:
    """``toggle_sticky(index)`` (Seiten-Controller) fuer den Eintrag im Rechtsklick-Menue."""

    def __init__(self, view: EditView, toggle_sticky: Callable[[int], None]) -> None:
        self._view = view
        self._toggle_sticky = toggle_sticky
        self.cut_action = self.copy_action = self.paste_action = None
        self.duplicate_action = self.delete_action = None

    def add_actions(self, menu) -> None:
        """Eintraege Ausschneiden … Löschen ins Menue „Bearbeiten“ (Entf nur am Geraetebild:
        ``delete_action`` gehoert dort zusaetzlich hin)."""
        K = QKeySequence.StandardKey
        self.cut_action = menu_action(menu, "edit-cut", tr("&Ausschneiden"), self.cut_selection)
        self.cut_action.setShortcut(QKeySequence(K.Cut))
        self.copy_action = menu_action(menu, "edit-copy", tr("&Kopieren"), self.copy_selection)
        self.copy_action.setShortcut(QKeySequence(K.Copy))
        self.paste_action = menu_action(menu, "edit-paste", tr("&Einfügen"), self.paste)
        self.paste_action.setShortcut(QKeySequence(K.Paste))
        self.duplicate_action = menu_action(menu, "edit-duplicate", tr("&Duplizieren"),
                                            self.duplicate_selection)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.delete_action = menu_action(menu, "edit-delete", tr("&Löschen"), self.delete_selection)
        self.delete_action.setShortcut(QKeySequence(K.Delete))
        self.delete_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)

    # --- Zwischenablage --------------------------------------------------------------

    def _items(self, refs: list[ControlRef]) -> list[edit.Item]:
        return edit.take_items(self._view.shown_ctx(), refs)

    def copy_selection(self) -> bool:
        items = [i for i in self._items(self._view.selected_refs())
                 if not edit.is_empty(i.kind, i.value)]
        if not items:
            self._view.say(tr("Nichts zum Kopieren gewählt"))
            return False
        clipboard.put_items(items)
        self._view.say(tr("{count} Element(e) kopiert", count=len(items)))
        return True

    def cut_selection(self) -> None:
        if self.copy_selection():
            self.delete_selection(label=tr("Ausschneiden"))

    def delete_selection(self, *_, label: str | None = None) -> None:
        ctx = self._view.shown_ctx()
        if edit.clear(ctx, self._view.selected_refs()):
            self._view.finish(ctx, label or tr("Löschen"))

    def paste(self) -> None:
        items, bad = clipboard.get_items()
        refs = self._view.selected_refs()
        if bad and not items:
            self._view.say(tr("Die Zwischenablage enthält keine gültigen Elemente"))
            return
        if not items or not refs:
            self._view.say(tr("Nichts einzufügen") if not items
                           else tr("Erst ein Ziel am Gerät wählen"))
            return
        target = min(refs, key=lambda r: (r.kind, r.index)) if len(refs) > 1 else refs[0]
        self._place(items, target, tr("Einfügen"))
        if bad:
            self._view.say(tr("{count} ungültige(s) Element(e) in der Zwischenablage "
                              "übersprungen", count=bad))

    def duplicate_selection(self) -> None:
        """Gewaehlte Elemente auf die naechsten freien Plaetze derselben Art."""
        if _typing():
            return
        ctx = self._view.shown_ctx()
        placed, missing = edit.duplicate(ctx, self._items(self._view.selected_refs()))
        if placed:
            self._view.finish(ctx, tr("Duplizieren"), placed)
        if missing:
            self._view.say(tr("{count} Element(e): kein freier Platz dahinter", count=missing))

    # --- Ziehen und Ablegen ----------------------------------------------------------

    def _place(self, items: list[edit.Item], target: ControlRef, label: str, *,
               move: bool = False) -> None:
        ctx = self._view.shown_ctx()
        result = edit.place(ctx, items, target, touch_only=LIVE_TYPES, move=move)
        if result.blocked is not None:
            dst, src = result.blocked
            self._view.say(tr("Nicht verschoben: {dst} kann nicht nach {src} "
                              "(mit Strg ziehen = kopieren)", dst=ref_name(dst),
                              src=ref_name(src)))
            return
        if result.placed:
            self._view.finish(ctx, label, result.placed)
        if result.skipped:
            self._view.say(tr("{count} Element(e) passen dort nicht hin", count=result.skipped))

    def controls_dropped(self, sources: list[ControlRef], target: ControlRef,
                         copy_: bool) -> None:
        """Ziehen zwischen Elementen: verschieben (Ziel und Quelle tauschen), Strg: kopieren."""
        ctx = self._view.shown_ctx()
        sources = [s for s in sources if edit.available(ctx, s) and not edit.locked(ctx, s)]
        items = [i for i in self._items(sources) if not edit.is_empty(i.kind, i.value)]
        if items:
            self._place(items, target, tr("Kopieren") if copy_ else tr("Verschieben"),
                        move=not copy_)

    def action_dropped(self, ref: ControlRef, action: dict) -> None:
        """Aktionsvorlage auf ``ref``: Taste bekommt sie (Bild bleibt), Regler als Dreh- oder
        Druckaktion, Rad als Drehaktion."""
        at = registry().get(action.get("type"))
        ctx = self._view.shown_ctx()
        value = edit.dropped_value(ctx, ref, action, at.kinds if at else {"press"}, LIVE_TYPES)
        if isinstance(value, edit.Refusal):
            self._view.say(tr(REFUSALS[value]))
            return
        edit.set_value(ctx, ref, value)
        self._view.finish(ctx, tr("{action} ablegen", action=action_label(action)), [ref])

    def apply_template(self, action: dict) -> None:
        """Doppelklick in der Aktionsliste: wie Ablegen auf das gewaehlte Element."""
        ref = self._view.selected
        if ref is None or not edit.available(self._view.shown_ctx(), ref):
            self._view.say(tr("Erst ein Element am Gerät wählen"))
        else:
            self.action_dropped(ref, action)  # Feld 1 einer Ordnerseite: Hinweis dort

    def files_dropped(self, ref: ControlRef, paths: list[Path]) -> None:
        """Dateien aus dem Dateimanager (z. B. ``.desktop``-Verknuepfungen) ablegen: die erste
        auf ``ref``, weitere auf die folgenden freien Touch-Felder; ein Rückgängig-Schritt."""
        if ref.kind not in FILE_KINDS:
            self._view.say(tr("Dateien bitte auf eine Taste ziehen"))
            return
        ctx = self._view.shown_ctx()
        if edit.locked(ctx, ref):
            self._view.say(tr(FOLDER_LOCKED))
            return
        placed = list(zip(edit.file_targets(ctx, ref), paths))
        for target, path in placed:
            edit.set_value(ctx, target, assignment_for(path))
        self._view.finish(ctx, tr("Dateien ablegen"), [t for t, _ in placed], current=ref,
                          now=True)
        if len(paths) > len(placed):
            self._view.say(tr("{count} Datei(en) ohne freies Feld nicht abgelegt",
                              count=len(paths) - len(placed)))

    # --- Rechtsklick -------------------------------------------------------------------

    def show_control_menu(self, ref: ControlRef, pos) -> None:
        with disposing(self.control_menu(ref)) as menu:
            menu.exec(pos)

    def control_menu(self, ref: ControlRef) -> QMenu:
        """Rechtsklick auf ein Element: Zwischenablage, Duplizieren, Löschen, Anheften."""
        menu = QMenu(self._view.dialog_parent())
        for action in (self.cut_action, self.copy_action, self.paste_action,
                       self.duplicate_action, self.delete_action):
            menu.addAction(action)
        self.paste_action.setEnabled(clipboard.has_items())
        ctx = self._view.shown_ctx()
        if ref.kind == ControlKind.TOUCH and ctx.page is not None and not ctx.page.folder:
            menu.addSeparator()
            pinned = edit.sticky(ctx, ref)
            text = (tr("Nicht mehr auf allen Seiten anheften") if pinned
                    else tr("Auf allen Seiten anheften"))
            a = menu_action(menu, "window-pin", text, lambda: self._toggle_sticky(ref.index))
            a.setEnabled(pinned or edit.get_value(ctx, ref) is not None)
        return menu
