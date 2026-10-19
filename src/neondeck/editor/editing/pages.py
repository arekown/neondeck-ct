"""Seiten und Arbeitsbereich bearbeiten: Seiten hinzufügen/entfernen/umbenennen/kopieren/
einfügen, Ordnerseiten, Sticky-Kacheln, Anordnen (Dialog und Reiter ziehen), LED-Farbe und
Leistenanzeige, das Rechtsklick-Menue der Seitenreiter. Die Aenderung am Profil macht
``profile.edit``; jede Aenderung wird gleich gespeichert (ein Rückgängig-Schritt)."""
from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

from ...core.i18n import N_, tr
from ...profile import edit
from ..dialogs.arrange_dialog import ArrangeDialog
from ..widgets.base import disposing, menu_action
from ..widgets.color_button import pick_color
from ..widgets.page_bar import PageBar
from . import clipboard
from .commit import CommitScheduler
from .history import ProfileHistory
from .navigation import Navigator

if TYPE_CHECKING:
    from .host import EditView

FOLDER_FIELD_HINT = N_("Feld 1 einer Ordnerseite ist „Zurück“ – die Belegung dort bleibt "
                       "gespeichert, ist im Ordner aber verdeckt")


class PageEditing:
    def __init__(self, view: EditView, history: ProfileHistory, commits: CommitScheduler,
                 navigator: Navigator, page_bar: PageBar) -> None:
        self._view = view
        self._history = history
        self._commits = commits
        self._navigator = navigator
        self._bar = page_bar
        self.copy_page_action = self.paste_page_action = None

    def add_actions(self, menu) -> None:
        """„Seite kopieren“ und „Seite einfügen“ ins Menue „Bearbeiten“."""
        self.copy_page_action = menu_action(menu, None, tr("Seite &kopieren"),
                                            partial(self.copy_page, None))
        self.paste_page_action = menu_action(menu, None, tr("Seite einf&ügen"), self.paste_page)

    def _commit(self, ctx: edit.EditContext, label: str, *, session: bool = True) -> None:
        if session:
            self._history.new_session()
        self._commits.commit_now(ctx.profile, label=label)
        self._view.sync_from_engine(force=True)

    def _page_at(self, index: int | None):
        """``(ctx, ws, i)`` fuer Reiter ``index`` (``None``: der gezeigte); ``ws`` ``None``,
        wenn es die Seite nicht gibt."""
        ctx = self._view.shown_ctx()
        ws = ctx.workspace
        i = self._bar.current() if index is None else index
        return ctx, (ws if ws is not None and 0 <= i < len(ws.touch_pages) else None), i

    # --- Seiten ------------------------------------------------------------------------

    def add_page(self) -> None:
        ctx = self._view.shown_ctx()
        if ctx.workspace is None:
            return
        index = edit.add_page(ctx.workspace)
        self._commits.commit_now(ctx.profile, label=tr("Seite hinzufügen"))
        self._navigator.show(ctx, ctx.workspace, index)  # neue Seite am Geraet zeigen

    def remove_page(self) -> None:
        ctx = self._view.shown_ctx()
        ws, page = ctx.workspace, ctx.page
        if ws is None or page is None or len(ws.touch_pages) <= 1:
            return
        if any(b is not None for b in page.buttons) and QMessageBox.question(
                self._view.dialog_parent(), tr("Seite entfernen"),
                tr("Die Seite „{name}“ ist belegt. Wirklich entfernen?",
                   name=page.name or page.id)) \
                != QMessageBox.StandardButton.Yes:
            return
        if not edit.remove_page(ws, page):
            self._view.say(tr("Die letzte normale Seite bleibt"))
            return
        self._commit(ctx, tr("Seite entfernen"), session=False)

    def rename_page(self) -> None:
        ctx = self._view.shown_ctx()
        page = ctx.page
        if page is None:
            return
        name, ok = QInputDialog.getText(self._view.dialog_parent(), tr("Seite umbenennen"),
                                        tr("Name:"), text=page.name)
        if ok and edit.rename_page(page, name):
            self._commit(ctx, tr("Seite umbenennen"), session=False)

    def copy_page(self, index: int | None = None) -> None:
        _ctx, ws, i = self._page_at(index)
        if ws is not None:
            page = ws.touch_pages[i]
            clipboard.put_page(page)
            self._view.say(tr("Seite „{name}“ kopiert", name=page.name or page.id))

    def paste_page(self) -> None:
        """Kopierte Seite hinter der gezeigten einfuegen (auch in einem anderen Arbeitsbereich
        oder Profil); bekommt eine neue Kennung."""
        try:
            page = clipboard.get_page()
        except clipboard.InvalidPage as e:
            self._view.say(tr("Seite in der Zwischenablage ist ungültig: {error}", error=e))
            return
        ctx = self._view.shown_ctx()
        ws = ctx.workspace
        if page is None or ws is None:
            self._view.say(tr("Keine Seite in der Zwischenablage"))
            return
        at = min(len(ws.touch_pages), self._bar.current() + 1)
        lost = edit.paste_page(ws, page, at)
        self._history.new_session()
        self._commits.commit_now(ctx.profile, label=tr("Seite einfügen"))
        self._navigator.show(ctx, ws, at)
        if lost:
            self._view.say(tr("{count} Ordner-Taste(n): die Ordnerseite gibt es hier nicht – "
                              "Ziel bitte neu wählen", count=lost))

    def toggle_folder(self, index: int | None = None) -> None:
        ctx, ws, i = self._page_at(index)
        if ws is None:
            return
        folder = edit.toggle_folder(ws, i)
        if folder is None:
            self._view.say(tr("Die letzte normale Seite kann kein Ordner werden"))
            return
        self._commit(ctx, tr("Ordnerseite") if folder else tr("Normale Seite"))
        buttons = ws.touch_pages[i].buttons
        if folder and buttons and buttons[0] is not None:
            self._view.say(tr(FOLDER_FIELD_HINT))

    def toggle_sticky(self, index: int) -> None:
        """Touch-Feld ``index`` auf allen (normalen) Seiten des Arbeitsbereichs anheften bzw.
        loesen (dann liegt die Belegung wieder auf der gezeigten Seite, wenn dort frei)."""
        ctx = self._view.shown_ctx()
        change = edit.toggle_sticky(ctx, index)
        if change is None:
            return
        if change.page_kept_own:
            self._view.say(tr("Die Seite hat hier eine eigene Belegung – sie gilt jetzt wieder"))
        self._commit(ctx, tr("Auf allen Seiten anheften") if change.pinned
                     else tr("Nicht mehr anheften"))

    # --- Anordnen ------------------------------------------------------------------------

    def open_arrange(self) -> None:
        self._commits.flush()
        view = self._view
        with disposing(ArrangeDialog(view.profile, view.engine.workspace_id,
                                     view.dialog_parent())) as dialog:
            if dialog.exec():
                self.apply_arrangement(dialog.workspace_order(), dialog.page_orders())

    def tab_moved(self, src: int, dst: int) -> None:
        ws = self._view.shown_ctx().workspace
        order = edit.moved_order(ws, src, dst) if ws is not None else None
        if order is not None:
            self.apply_arrangement(None, {ws.id: order})

    def apply_arrangement(self, workspace_order: list[str] | None,
                          page_orders: dict[str, list[str]]) -> None:
        """Neue Reihenfolge uebernehmen (ein Rückgängig-Schritt); die gezeigte Seite bleibt
        gezeigt, auch wenn sie jetzt eine andere Nummer hat."""
        self._commits.flush()
        view = self._view
        profile, ws, i = view.profile, view.engine.workspace, view.engine.page_index
        shown = ws.touch_pages[i].id if ws is not None and 0 <= i < len(ws.touch_pages) else None
        try:
            changed = edit.apply_arrangement(profile, workspace_order, page_orders)
        except ValueError as e:
            view.say(str(e))
            view.sync_from_engine(force=True)
            return
        if not changed:
            return
        self._history.new_session()
        self._commits.commit_now(profile, label=tr("Anordnen"))
        self._navigator.keep_page(ws, shown)
        view.sync_from_engine(force=True)
        view.say(tr("Neue Reihenfolge übernommen"))

    # --- Arbeitsbereich ------------------------------------------------------------------

    def choose_led_color(self) -> None:
        ws = self._view.shown_ctx().workspace
        if ws is None:
            return
        color = pick_color(self._view.dialog_parent(), ws.led_color,
                           tr("LED-Farbe des Arbeitsbereichs"))
        if color is not None:
            self.set_led_color(color)

    def set_led_color(self, color: str | None) -> None:
        ctx = self._view.shown_ctx()
        if ctx.workspace is not None and edit.set_led_color(ctx.workspace, color):
            self._commit(ctx, tr("LED-Farbe"), session=False)

    def set_strip_mode(self, side: str, mode: str, *_) -> None:
        """Anzeige der linken/rechten Leiste des gezeigten Arbeitsbereichs
        (``Workspace.strip_left``/``strip_right``: Regler oder Systemlast)."""
        ctx = self._view.shown_ctx()
        if ctx.workspace is not None and edit.set_strip_mode(ctx.workspace, side, mode):
            self._commit(ctx, tr("Leistenanzeige"), session=False)

    # --- Rechtsklick auf einen Reiter ----------------------------------------------------

    def show_page_menu(self, pos) -> None:
        with disposing(self.page_menu(self._bar.tabs.tabAt(pos))) as menu:
            menu.exec(self._bar.tabs.mapToGlobal(pos))

    def page_menu(self, index: int) -> QMenu:
        """Rechtsklick auf einen Seitenreiter: Seite kopieren/einfuegen, Ordnerseite …"""
        menu = QMenu(self._view.dialog_parent())
        _ctx, ws, _i = self._page_at(index)
        valid = ws is not None
        if valid and index != self._bar.current():
            self._bar.select(index)  # Aktionen gelten der angeklickten Seite
        menu_action(menu, "edit-copy", tr("Seite kopieren"),
                    lambda: self.copy_page(index)).setEnabled(valid)
        menu_action(menu, "edit-paste", tr("Seite einfügen"),
                    self.paste_page).setEnabled(clipboard.has_page())
        menu.addSeparator()
        folder = valid and ws.touch_pages[index].folder
        menu_action(menu, "folder",
                    tr("Normale Seite") if folder else tr("Als Ordnerseite"),
                    lambda: self.toggle_folder(index)).setEnabled(valid)
        menu_action(menu, "edit-rename", tr("Umbenennen …"), self.rename_page).setEnabled(valid)
        menu_action(menu, "list-remove", tr("Entfernen"),
                    self.remove_page).setEnabled(valid and len(ws.touch_pages) > 1)
        return menu
