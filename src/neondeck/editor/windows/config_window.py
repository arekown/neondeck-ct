"""Einstellungsfenster: Profil/Arbeitsbereich/Seite waehlen, Element anklicken, belegen.

Das Fenster zeigt immer den Arbeitsbereich und die Seite, die auch das Geraet zeigt
(Auswahl hier steuert die Engine; Blaettern am Geraet zieht das Fenster nach). Aenderungen
gehen sofort ins Profil der Engine, gespeichert und neu gezeichnet wird kurz danach gebuendelt
(``commits``). Unter dem Geraet liegt der Inspector des gewaehlten Elements, rechts die
Aktionsliste (ziehen oder doppelklicken).

Das Fenster baut die Teile zusammen und verbindet sie; die Arbeit machen Controller mit
klarer Schnittstelle (``editing.host.EditView``): ``edit`` (Elemente, Zwischenablage, Ziehen),
``pages`` (Seiten, Sticky, Ordner, Anordnen, LED, Leisten), ``undoing`` (Rückgängig),
``navigator`` (Profil, Arbeitsbereich, Seite), ``extras`` (Dialoge, Vorlagen, Versionen,
Export/Import), ``theme_menu`` (Menue „Ansicht“). Profilwechsel macht immer der Dienst
(``switch_profile``).

Im Editor-Prozess (``editor.main``) sind ``engine`` und ``store`` die API-Gegenstuecke aus
``editor.remote``; das Fenster selbst kennt nur deren Engine-/Speicher-Schnittstelle.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...api.protocol import event_from_dict
from ...core.i18n import N_, tr
from ...device.layout import ControlKind, ControlRef
from ...engine.kinds import LIVE_TYPES
from ...engine.painter import action_label
from ...profile import edit
from ...profile.edit import EditContext
from ...profile.model import Profile
from ...ui.common import STATUS_LONG_MS, STATUS_MS
from ..dialogs.simulate import Simulator
from ..editing.commit import CommitScheduler
from ..editing.controls import FOLDER_LOCKED, ControlEditing
from ..editing.history import ProfileHistory
from ..editing.navigation import Navigator
from ..editing.pages import PageEditing
from ..editing.undoing import UndoController
from ..widgets.action_library import ActionLibrary
from ..widgets.assignment_editor import AssignmentEditor
from ..widgets.base import menu_action
from ..widgets.device_view import DeviceView
from ..widgets.labels import ref_name
from ..widgets.nav_targets import NavTargets
from ..widgets.page_bar import PageBar
from ..widgets.param_widgets import Catalog
from .extras import ExtrasController
from .profile_toolbar import ProfileToolbar
from .theme_menu import ThemeMenu

if TYPE_CHECKING:  # nur Typen: im Editor-Prozess RemoteEngine/RemoteStore (ohne engine.py)
    from ...api.contracts import EditorBackend, ProfileRepository, ServiceLink

TITLE = N_("Neondeck CT – Einstellungen")
WINDOW_SIZE = (1460, 980)
FOLLOW_MS = 500         # Blaettern/Profilwechsel am Geraet nachziehen
INSPECTOR_HEIGHT = 460
INSPECTOR_MIN_HEIGHT = 200
LIBRARY_WIDTH = 270
LIBRARY_MIN_WIDTH = 200
STICKY_NOTE = N_("Angeheftet: diese Belegung gilt auf allen normalen Seiten des Arbeitsbereichs.")
OFFLINE_TEXT = N_("Verbindung zum Dienst getrennt – Änderungen werden nachgereicht")
SIMULATE_TEXT = N_("SIMULATION – Klicks am Gerätebild wirken wie am Gerät")


def _add_menu(window: QMainWindow, title: str) -> QMenu:
    """Menue als selbst erzeugtes QMenu (wie ``menu_action``)."""
    menu = QMenu(title, window)
    window.menuBar().addMenu(menu)
    return menu


def _status_label(window: QMainWindow, name: str, text: str) -> QLabel:
    """Dauerhinweis rechts in der Statuszeile (anfangs versteckt)."""
    label = QLabel(tr(text))
    label.setObjectName(name)
    window.statusBar().addPermanentWidget(label)
    label.hide()
    return label


class ConfigWindow(QMainWindow):
    def __init__(self, store: ProfileRepository, engine: EditorBackend,
                 switch_profile: Callable[[str], None], parent=None, *,
                 on_theme: Callable[[str, bool], None] | None = None,
                 service: ServiceLink | None = None):
        super().__init__(parent)
        self.store = store
        self.engine = engine
        self.service = service  # nur mit Dienst (Editor-Prozess): Anfragen an die API
        self.selected: ControlRef | None = None
        self._multi: list[ControlRef] = []      # Mehrfachauswahl (Strg-Klick)
        self._shown: tuple | None = None
        self._edit_ctx: EditContext | None = None  # wo das Element im Editor liegt
        self._view: EditContext | None = None      # was das Fenster gerade zeigt
        self.catalog = Catalog(service.request_async if service is not None else None, self)
        self.history = ProfileHistory()
        self.commits = CommitScheduler(store, engine, self.history, self.say, self)
        self.navigator = Navigator(self, self.commits, switch_profile)
        self.undoing = UndoController(self, self.history, self.commits)
        self.toolbar = ProfileToolbar()
        self.page_bar = PageBar()
        self.pages = PageEditing(self, self.history, self.commits, self.navigator, self.page_bar)
        self.edit = ControlEditing(self, self.pages.toggle_sticky)
        self.setWindowTitle(tr(TITLE))
        self.setWindowIcon(QIcon.fromTheme("input-keyboard"))
        self.resize(*WINDOW_SIZE)
        self.addToolBar(self.toolbar)
        self._build_menus(on_theme)
        self.setCentralWidget(self._build_central())
        self._build_status()
        self._connect()
        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self.sync_from_engine)
        self.reload_profiles()
        self.sync_from_engine(force=True)

    def _build_menus(self, on_theme) -> None:
        self.profile_menu = _add_menu(self, tr("&Profil"))
        self.edit_menu = _add_menu(self, tr("&Bearbeiten"))
        self.undoing.add_actions(self.edit_menu)
        self.edit_menu.addSeparator()
        self.edit.add_actions(self.edit_menu)
        self.edit_menu.addSeparator()
        self.pages.add_actions(self.edit_menu)
        self.theme_menu = ThemeMenu(_add_menu(self, tr("&Ansicht")), on_theme, self)
        self.extras = ExtrasController(self, self.history, self.commits, self.navigator,
                                       self.catalog, set_theme=self.theme_menu.set_theme)
        x = self.extras
        for entry in (
                ("configure", tr("Profile und Arbeitsbereiche &verwalten …"), x.open_profile_manager),
                ("view-sort", tr("Arbeitsbereiche und Seiten &anordnen …"), self.pages.open_arrange),
                ("document-properties", tr("Profil-&Einstellungen …"), x.open_profile_settings),
                ("document-import", tr("Windows-Profil &importieren …"), x.import_windows_profile),
                ("list-add", tr("&Vorlage einfügen …"), x.open_template_dialog),
                None,
                ("document-open-recent", tr("&Versionen …"), x.open_versions),
                ("document-export", tr("Profil e&xportieren …"), x.export_profile),
                ("document-import", tr("Profil (.ndprofile) i&mportieren …"),
                 x.import_shared_profile)):
            if entry is None:
                self.profile_menu.addSeparator()
            else:
                menu_action(self.profile_menu, *entry)
        self.extras_menu = _add_menu(self, tr("E&xtras"))
        menu_action(self.extras_menu, "configure", tr("&Einstellungen …"), x.open_settings_page)
        menu_action(self.extras_menu, "dialog-information", tr("&Diagnose …"), x.open_diagnose)
        menu_action(self.extras_menu, None, tr("E&rsteinrichtung …"), x.open_first_run)

    def _build_central(self) -> QSplitter:
        """Links Seitenreiter, Geraetebild und darunter der Inspector; rechts die Aktionen."""
        self.device_view = DeviceView()
        self.device_view.addAction(self.edit.delete_action)  # Entf nur am Geraetebild
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.addWidget(self.page_bar)
        top_layout.addWidget(self.device_view, 1)
        self.editor = AssignmentEditor()
        # nie unter die Wunschhoehe druecken (Zeilen ueberlappten sonst): lieber rollen
        self.editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(INSPECTOR_MIN_HEIGHT)
        scroll.setWidget(self.editor)
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(top)
        left.addWidget(scroll)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        left.setChildrenCollapsible(False)
        left.setSizes([self.height() - INSPECTOR_HEIGHT, INSPECTOR_HEIGHT])
        self.library = ActionLibrary()
        self.library.setMinimumWidth(LIBRARY_MIN_WIDTH)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.library)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([self.width() - LIBRARY_WIDTH, LIBRARY_WIDTH])
        return splitter

    def _build_status(self) -> None:
        """Dauerhinweise rechts in der Statuszeile: Dienst getrennt, Simulieren."""
        self.simulator = Simulator(
            self.device_view, lambda event: self.engine.handle(event_from_dict(event)), self)
        self.toolbar.addWidget(self.simulator.button)
        self.offline_label = _status_label(self, "offline", OFFLINE_TEXT)
        self.simulate_label = _status_label(self, "simulate", SIMULATE_TEXT)
        self.simulator.toggled.connect(self.simulate_label.setVisible)

    def _connect(self) -> None:
        bar, tabs, view, ed = self.toolbar, self.page_bar.tabs, self.device_view, self.edit
        bar.profile_chosen.connect(self.navigator.choose_profile)
        bar.workspace_chosen.connect(self.navigator.choose_workspace)
        bar.arrange_button.clicked.connect(self.pages.open_arrange)
        bar.template_button.clicked.connect(self.extras.open_template_dialog)
        bar.led_choose_action.triggered.connect(self.pages.choose_led_color)
        bar.led_reset_action.triggered.connect(lambda: self.pages.set_led_color(None))
        for (side, mode), action in bar.strip_actions.items():
            action.triggered.connect(partial(self.pages.set_strip_mode, side, mode))
        tabs.currentChanged.connect(self.navigator.choose_page)
        tabs.tabMoved.connect(self.pages.tab_moved)
        tabs.tabBarDoubleClicked.connect(lambda _i: self.pages.rename_page())
        tabs.customContextMenuRequested.connect(self.pages.show_page_menu)
        self.page_bar.add_button.clicked.connect(self.pages.add_page)
        self.page_bar.remove_button.clicked.connect(self.pages.remove_page)
        self.page_bar.rename_button.clicked.connect(self.pages.rename_page)
        view.selection_changed.connect(self._selection_changed)
        view.selected.connect(self.select)
        view.action_dropped.connect(ed.action_dropped)
        view.files_dropped.connect(ed.files_dropped)
        view.controls_dropped.connect(ed.controls_dropped)
        view.context_requested.connect(ed.show_control_menu)
        self.editor.changed.connect(self._edited)
        self.editor.test_requested.connect(self._test)
        self.library.activated.connect(ed.apply_template)

    # --- EditView ------------------------------------------------------------------------

    def dialog_parent(self) -> QWidget:
        return self

    def say(self, text: str, long: bool = False) -> None:
        """Meldung in der Statuszeile (``long``: Aufzaehlungen, etwas laenger sichtbar)."""
        self.statusBar().showMessage(text, STATUS_LONG_MS if long else STATUS_MS)

    def set_offline(self, offline: bool) -> None:
        """Dauerhafter Hinweis in der Statuszeile, solange der Dienst nicht erreichbar ist."""
        self.offline_label.setVisible(offline)

    @property
    def profile(self) -> Profile:
        return self.engine.profile

    def profile_name(self, pid: str) -> str:
        return self.toolbar.profile_name(pid)

    def _current(self) -> EditContext:
        ws = self.engine.workspace
        i = self.engine.page_index
        page = ws.touch_pages[i] if ws and 0 <= i < len(ws.touch_pages) else None
        return EditContext(self.profile, ws, page)

    def shown_ctx(self) -> EditContext:
        """Die Stelle, die das Fenster zeigt; Klicks und Ablegen beziehen sich darauf,
        auch wenn das Geraet seit dem letzten Nachziehen weitergeblaettert hat."""
        return self._view or self._current()

    def reload_profiles(self) -> None:
        """Profilliste neu einlesen (Namen aus den Dateien)."""
        ids = self.store.list()
        current = self.profile.id
        if current not in ids:
            ids.append(current)
        self.toolbar.set_profiles(
            [(pid, (self.profile.name or pid) if pid == current else self.store.name(pid))
             for pid in ids], current)

    def sync_from_engine(self, force: bool = False) -> None:
        """Fenster an Arbeitsbereich/Seite/Profil der Engine angleichen."""
        ws = self.engine.workspace
        state = (id(self.profile), self.engine.workspace_id, self.engine.page_index,
                 tuple((w.id, w.name) for w in self.profile.workspaces),
                 tuple((p.name, p.folder) for p in ws.touch_pages) if ws else ())
        if not force and state == self._shown:
            return
        replaced = self._shown is not None and state[0] != self._shown[0]
        if replaced:
            self.flush()  # Profil am Geraet gewechselt: Ausstehendes vorher speichern
            self.reload_profiles()
        self.history.follow(self.profile, first=self._shown is None, replaced=replaced)
        self._shown = state
        self._view = self._current()
        self.toolbar.show_workspace(self.profile, self.engine.workspace_id, ws)
        self.page_bar.show_pages(ws, self.engine.page_index, self._view.page is not None)
        self.device_view.set_view(self.profile, ws, self._view.page)
        self.load_editor()

    def load_editor(self) -> None:
        """Inspector fuer das gewaehlte Element an der gezeigten Stelle."""
        ref = self.selected
        ctx = self.shown_ctx()
        if ref is not None and not edit.available(ctx, ref):
            ref = None
        # Aenderungen aus dem Editor gehen an genau diese Stelle, auch wenn das Geraet
        # inzwischen weitergeblaettert hat (das Fenster zieht erst mit dem Timer nach).
        self._edit_ctx = ctx
        ws = ctx.workspace
        self.editor.set_nav_targets(NavTargets(
            workspaces=[(w.id, w.name or w.id) for w in ctx.profile.workspaces],
            profiles=self.toolbar.profile_entries(),
            folder_pages=[(p.id, p.name or p.id) for p in (ws.touch_pages if ws else [])
                          if p.folder],
            catalog=self.catalog))
        if ref is not None and edit.locked(ctx, ref):
            self.editor.set_target(ref, None, locked=tr(FOLDER_LOCKED))
        else:
            note = tr(STICKY_NOTE) if ref is not None and edit.sticky(ctx, ref) else None
            self.editor.set_target(ref, edit.get_value(ctx, ref) if ref else None, note=note)
        multi = [r for r in self._multi if edit.available(ctx, r)]
        self.device_view.set_selection(multi if ref in multi else ref)

    # --- Auswahl ---------------------------------------------------------------------

    def select(self, ref: ControlRef) -> None:
        if ref.kind == ControlKind.STRIP:
            ref = ControlRef(ControlKind.KNOB, ref.index)
        self.selected = ref
        if ref not in self._multi:
            self._multi = [ref]
        self.history.new_session()
        self.load_editor()

    def _selection_changed(self, refs: list) -> None:
        self._multi = list(refs)

    def selected_refs(self) -> list[ControlRef]:
        ctx = self.shown_ctx()
        refs = self.device_view.selection() or ([self.selected] if self.selected else [])
        return [r for r in refs if edit.available(ctx, r) and not edit.locked(ctx, r)]

    def finish(self, ctx: EditContext, label: str, select: list[ControlRef] | None = None, *,
               current: ControlRef | None = None, now: bool = False) -> None:
        self.history.new_session()
        self.device_view.refresh()
        self.commits.schedule(ctx.profile, label=label)
        if now:
            self.commits.flush()
        if select:
            self.selected = current or select[-1]
            self._multi = list(select)
        self.load_editor()

    # --- Inspector ---------------------------------------------------------------------

    def _edited(self, value) -> None:
        ref, ctx = self.editor.ref, self._edit_ctx
        if ref is not None and ctx is not None:
            edit.set_value(ctx, ref, value)
            self.device_view.refresh()
            merge = (self.history.session, ref, id(ctx.page))  # Eingaben an einer Stelle: ein Schritt
            self.commits.schedule(ctx.profile, label=tr("{name} ändern", name=ref_name(ref)), merge=merge)

    def _test(self) -> None:
        ref = self.editor.ref
        action, steps = self.editor.test_action()
        t = (action or {}).get("type")
        if ref is None or not t or t in LIVE_TYPES:  # Anzeigen fuehren nichts aus
            self.say(tr("Keine Aktion zum Testen"))
            return
        self.engine.trigger(ref, action, steps=steps)
        self.say(tr("Ausgelöst: {action} ({name})", action=action_label(action),
                     name=ref_name(ref)))

    # --- Fenster -----------------------------------------------------------------------------

    def flush(self) -> None:
        """Ausstehende Aenderungen speichern und am Geraet anzeigen (``commits.flush``)."""
        self.commits.flush()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload_profiles()
        self.sync_from_engine(force=True)
        self._follow_timer.start(FOLLOW_MS)

    def hideEvent(self, event) -> None:
        self._follow_timer.stop()
        self.flush()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.flush()
        super().closeEvent(event)  # nur verstecken: das Fenster bleibt fuer schnelles Oeffnen
