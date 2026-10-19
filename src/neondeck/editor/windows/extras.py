"""Dialoge und Zusaetze des Einstellungsfensters.

Menue „Profil“: Profile und Arbeitsbereiche verwalten, Profil-Einstellungen, Windows-Profil
importieren, „Vorlage einfügen …“ (auch als Knopf in der Kopfzeile: angekreuzte Vorlagen als
Arbeitsbereiche ins gezeigte Profil, mit Rückgängig), Versionen (Snapshots ansehen, eines
wiederherstellen), Profil als ``.ndprofile`` exportieren und importieren. Menue „Extras“:
Seiten „Einstellungen“ und „Diagnose“, Ersteinrichtung.

Was den Dienst braucht (Versionen, Einstellungen, Diagnose), geht ueber ``service.request``;
ohne Dienst (Fenster an einer lokalen Engine) prueft die Diagnose nur lokal, der Rest meldet
sich in der Statuszeile.
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QVBoxLayout, QWidget

from ...core.i18n import N_, tr
from ...profile import share, templates
from ...profile.ids import imported_dir
from ...profile.model import Profile
from ...ui.common import DRAIN_S, Request
from ..dialogs.first_run import FirstRunWizard
from ..dialogs.profile_settings import ProfileSettingsDialog
from ..dialogs.template_picker import TemplateDialog
from ..dialogs.versions_dialog import VersionsDialog
from ..editing.commit import CommitScheduler
from ..editing.history import ProfileHistory
from ..editing.navigation import Navigator
from ..widgets.base import close_buttons, disposing
from ..widgets.param_widgets import Catalog
from .diagnose_page import DiagnosePage
from .profile_manager import ProfileManager
from .settings_page import SettingsPage

if TYPE_CHECKING:
    from ..editing.host import EditView

log = logging.getLogger(__name__)

NEEDS_SERVICE = N_("Nur mit laufendem Dienst möglich")
PAGE_DIALOG_SIZE = (760, 640)


def _share_filter(extensions: tuple[str, ...] = (share.EXTENSION,)) -> str:
    return tr("Neondeck-CT-Profil ({patterns})",
              patterns=" ".join(f"*{ext}" for ext in extensions))


def _quoted(names) -> str:
    return ", ".join(f"„{n}“" for n in names)


class ExtrasController:
    """``set_theme(name)`` (Menue „Ansicht“) fuer die Ersteinrichtung; ``profiles_changed()``
    nach Aenderungen in der Profilverwaltung."""

    def __init__(self, view: EditView, history: ProfileHistory, commits: CommitScheduler,
                 navigator: Navigator, catalog: Catalog, *,
                 set_theme: Callable[[str], None]) -> None:
        self._view = view
        self._history = history
        self._commits = commits
        self._navigator = navigator
        self._catalog = catalog
        self._set_theme = set_theme

    def _api(self) -> Request | None:
        service = self._view.service
        return service.request if service is not None else None

    def _parent(self) -> QWidget:
        return self._view.dialog_parent()

    def _page_dialog(self, title: str, page: QWidget) -> None:
        with disposing(QDialog(self._parent())) as dialog:
            dialog.setWindowTitle(title)
            dialog.resize(*PAGE_DIALOG_SIZE)
            layout = QVBoxLayout(dialog)
            layout.addWidget(page, 1)
            layout.addWidget(close_buttons(dialog))
            dialog.exec()

    # --- Extras ------------------------------------------------------------------------

    def open_settings_page(self) -> None:
        request = self._api()
        if request is None:
            self._view.say(tr(NEEDS_SERVICE))
            return
        page = SettingsPage(request)
        page.load()
        self._page_dialog(tr("Einstellungen"), page)

    def open_diagnose(self) -> None:
        page = DiagnosePage(self._api())
        page.refresh()
        self._page_dialog(tr("Diagnose"), page)

    def open_first_run(self) -> None:
        with disposing(FirstRunWizard(self._api(), self._set_theme, self.insert_templates,
                                      self._view.say, self._parent())) as wizard:
            wizard.exec()

    # --- Profilverwaltung ----------------------------------------------------------------

    def make_profile_manager(self) -> ProfileManager:
        self._commits.flush()
        view = self._view
        manager = ProfileManager(view.store, view.engine, self._commits.commit_now,
                                 self._navigator.switch_to, self._parent())
        manager.changed.connect(self._profiles_changed)
        return manager

    def _profiles_changed(self) -> None:
        self._view.reload_profiles()
        self._view.sync_from_engine(force=True)

    def open_profile_manager(self) -> None:
        with disposing(self.make_profile_manager()) as manager:
            manager.exec()

    def import_windows_profile(self) -> None:
        with disposing(self.make_profile_manager()) as manager:
            manager.import_profile()

    def open_profile_settings(self) -> None:
        """Anwendungen (Dynamic Mode), automatisch aktivieren, halten – fuer das gezeigte
        Profil."""
        profile = self._view.shown_ctx().profile
        with disposing(ProfileSettingsDialog(profile, self._catalog, self._parent())) as dialog:
            if dialog.exec() == ProfileSettingsDialog.DialogCode.Accepted and \
                    dialog.apply(profile):
                self._commits.commit_now(profile, label=tr("Profil-Einstellungen"))

    # --- Vorlagen ----------------------------------------------------------------------

    def open_template_dialog(self) -> None:
        profile, ws = self._view.profile, self._view.shown_ctx().workspace
        with disposing(TemplateDialog(profile.name or profile.id,
                                      (ws.name or ws.id) if ws is not None else None,
                                      self._parent())) as dialog:
            chosen = dialog.chosen() if dialog.exec() else None
            pages_only = dialog.pages_only()
        if chosen and pages_only:
            self.insert_template_pages(chosen)
        elif chosen:
            self.insert_templates(chosen)

    def insert_template_pages(self, template_ids: list[str]) -> list[str]:
        """Nur die Seiten der Vorlagen in den gezeigten Arbeitsbereich (ein Rückgängig-
        Schritt) und die erste neue Seite zeigen."""
        self._commits.flush()
        ctx = self._view.shown_ctx()
        ws = ctx.workspace
        if ws is None:
            return []
        first = len(ws.touch_pages)
        try:
            names = templates.insert_pages(ws, template_ids)
        except ValueError as e:
            self._view.say(tr("Vorlage nicht eingefügt: {error}", error=e))
            return []
        if not names:
            return []
        self._history.new_session()
        self._commits.commit_now(ctx.profile, label=tr("Vorlagen-Seiten einfügen"))
        self._navigator.show(ctx, ws, first)
        self._view.say(tr("{count} Seite(n) eingefügt: {names}", count=len(names),
                            names=_quoted(names)), long=True)
        return names

    def insert_templates(self, template_ids: list[str]) -> list[templates.Inserted]:
        """Vorlagen ins gezeigte Profil einfuegen (ein Rückgängig-Schritt, vorher Version)
        und den ersten neuen Arbeitsbereich zeigen."""
        self._commits.flush()
        profile = self._view.profile
        try:
            inserted = templates.insert_into(profile, template_ids)
        except ValueError as e:
            self._view.say(tr("Vorlage nicht eingefügt: {error}", error=e))
            return []
        if not inserted:
            return []
        self._history.new_session()
        self._commits.commit_now(profile, label=tr("Vorlage einfügen"))
        self._navigator.show_workspace(profile, inserted[0].workspace_id)
        names = _quoted(i.name for i in inserted)
        keyless = [i.name for i in inserted if i.round_code is None]
        text = tr("Eingefügt: {names} – runde Tasten schalten um", names=names)
        if keyless:
            text = tr("Eingefügt: {names}. Keine runde Taste mehr frei für {keyless} – "
                      "Auswahl über die Kopfzeile", names=names, keyless=_quoted(keyless))
        self._view.say(text, long=True)
        return inserted

    # --- Versionen ---------------------------------------------------------------------

    def open_versions(self) -> None:
        if self._api() is None:
            self._view.say(tr(NEEDS_SERVICE))
            return
        self._commits.flush()
        with disposing(self.make_versions_dialog(self._view.shown_ctx().profile)) as dialog:
            dialog.exec()

    def make_versions_dialog(self, profile: Profile) -> VersionsDialog:
        dialog = VersionsDialog(self._api(), profile.id, profile.name, self._parent(),
                                before_restore=self._before_restore)
        dialog.restored.connect(lambda _pid: self._view.reload_profiles())
        return dialog

    def _before_restore(self) -> None:
        """Ausstehende Aenderungen erst speichern: sonst ueberschriebe der Editor die
        wiederhergestellte Version gleich wieder."""
        self._commits.flush()
        if self._view.service is not None:
            self._view.service.drain(DRAIN_S)

    # --- Export / Import ---------------------------------------------------------------

    def export_profile(self) -> None:
        profile = self._view.shown_ctx().profile
        start = str(Path.home() / f"{profile.id}{share.EXTENSION}")
        path, _ = QFileDialog.getSaveFileName(self._parent(), tr("Profil exportieren"),
                                              start, _share_filter())
        if path:
            self.export_profile_to(Path(path))

    def export_profile_to(self, path: Path) -> bool:
        self._commits.flush()
        if path.suffix != share.EXTENSION:
            path = path.with_name(path.name + share.EXTENSION)
        profile = self._view.shown_ctx().profile
        try:
            missing = share.export_profile(profile, path)
        except OSError as e:
            log.warning("Export nach %s fehlgeschlagen: %s", path, e)
            QMessageBox.warning(self._parent(), tr("Export fehlgeschlagen"), str(e))
            return False
        note = tr(" – {count} Bild(er) nicht gefunden", count=len(missing)) if missing else ""
        self._view.say(tr("Profil „{name}“ exportiert: {path}", name=profile.name or profile.id,
                          path=path) + note)
        return True

    def import_shared_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self._parent(), tr("Profil importieren"),
                                              str(Path.home()),
                                              _share_filter(share.IMPORT_EXTENSIONS))
        if path:
            self.import_shared_profile_from(Path(path))

    def import_shared_profile_from(self, path: Path) -> Profile | None:
        """Als neues Profil anlegen (Bilder nach ``imported/<id>/``) und aktivieren."""
        store = self._view.store
        try:
            profile = share.import_profile(path, store.list())
        except (ValueError, OSError) as e:
            log.warning("Import von %s fehlgeschlagen: %s", path, e)
            QMessageBox.warning(self._parent(), tr("Import fehlgeschlagen"), str(e))
            return None
        try:
            store.save(profile)
        except OSError as e:  # lokaler Speicher; der Dienst meldet Fehler selbst
            shutil.rmtree(imported_dir(profile.id), ignore_errors=True)
            QMessageBox.warning(self._parent(), tr("Import fehlgeschlagen"), str(e))
            return None
        self._navigator.switch_to(profile.id)
        self._view.say(tr("Profil „{name}“ importiert", name=profile.name or profile.id))
        return profile
