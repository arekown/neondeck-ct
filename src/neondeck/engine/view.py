"""Ansicht und Navigation (ohne Qt): Arbeitsbereich, Seite, Ordner, dynamische Ordner und die
gemerkte Ansicht je Profil.

``ViewController.call`` ist das Ziel aller Navigationsaktionen (``engine_call``): eine Tabelle
Name -> Methode. Jeder Ansichtswechsel verwirft Gesammeltes und angefangene Gesten der alten
Belegung (``new_view``, R24/R25) und meldet sich ueber ``on_view``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from functools import partial

from ..core.values import parse_view
from ..profile.model import Profile
from .controls import ControlResolver
from .navigation_state import FolderLevel, find_page, first_normal, page_at
from .ports import EngineHooks, Redraw
from .state import EngineState

log = logging.getLogger(__name__)

# Seitenwechsel: aus einem dynamischen Ordner heraus von der Seite darunter aus
PAGE_TARGETS = frozenset({"page_next", "page_previous", "page", "folder"})

ViewSnapshot = tuple[Profile, str, int, dict, list[FolderLevel], int]


class ViewController:
    """Wechselt die Ansicht in ``state``; ``views`` ist die zuletzt aktive Ansicht je
    Profil-ID (Arbeitsbereich, Seite), auch ueber Neustart (``settings.last_pages``)."""

    def __init__(self, state: EngineState, controls: ControlResolver,
                 hooks: EngineHooks, redraw: Redraw, *, new_view: Callable[[], None],
                 clear_gestures: Callable[[], None], knobs_reassigned: Callable[[], None],
                 reset_caches: Callable[[], None]) -> None:
        self._state = state
        self._controls = controls
        self._folders = controls.folders
        self._dynamic = controls.dynamic
        self._hooks = hooks
        self._redraw = redraw
        self._new_view = new_view
        self._clear_gestures = clear_gestures
        self._knobs_reassigned = knobs_reassigned
        self._reset_caches = reset_caches
        self.views: dict[str, tuple[str, int]] = {}
        self._targets: dict[str, Callable[[dict], None]] = {
            "page_next": partial(self._step, 1), "page_previous": partial(self._step, -1),
            "page": self._page, "folder": self._folder,
            "workspace": lambda params: self.set_workspace(params.get("id")),
            "dynamic_folder": self._dynamic_folder,
            "folder_back": lambda params: self.folder_back(),
            "open_config": self._open_config, "profile": self._profile}

    # --- Profil --------------------------------------------------------------------------

    def load_views(self, views: dict | None) -> None:
        """Gemerkte Ansichten aus den Einstellungen (ungueltige Eintraege fallen weg)."""
        for pid, v in (views or {}).items():
            view = parse_view(v, min_page=None)
            if view is not None:
                self.views[pid] = view

    def reset(self, profile: Profile) -> None:
        """``profile`` von vorn zeigen: gemerkte Ansicht, sonst Heim-Arbeitsbereich, Seite 1;
        Ordner, Rueckmeldungen, Stoppuhren und Bild-Caches verfallen."""
        self._new_view()
        self._folders.clear()
        self._dynamic.close()
        st = self._state
        st.profile = profile
        ids = [w.id for w in profile.workspaces]
        st.workspace_id = profile.home_workspace if profile.home_workspace in ids else (
            ids[0] if ids else "")
        st.page_index = first_normal(st.workspace)
        self._restore_view(profile)
        st.feedback.clear()
        self._controls.clear_stopwatches()
        self._reset_caches()

    def _restore_view(self, profile: Profile) -> None:
        """Gemerkte Ansicht des Profils wiederherstellen (fehlt der Arbeitsbereich: Heim,
        fehlt die Seite oder ist sie ein Ordner: erste normale Seite)."""
        ws_id, page = self.views.get(profile.id, (None, 0))
        ws = next((w for w in profile.workspaces if w.id == ws_id), None)
        if ws is None:
            return
        self._state.workspace_id = ws.id
        p = page_at(ws, page)
        self._state.page_index = page if p is not None and not p.folder else first_normal(ws)

    def load(self, profile: Profile, *, keep_view: bool) -> None:
        """Neues Profil (siehe ``Engine.set_profile``); ohne Neuzeichnen."""
        st = self._state
        if keep_view and any(w.id == st.workspace_id for w in profile.workspaces):
            # Speichern im Editor ist kein Ansichtswechsel (R26): Gesten und Beruehrungen
            # laufen weiter, solange ihre Belegung gleich bleibt (Inhaltsvergleich).
            before = self._controls.page()
            st.profile = profile
            st.page_index = self._folders.keep(st.workspace, st.page_index)
            after = self._controls.page()
            if (before.id if before else None) != (after.id if after else None):
                self._clear_gestures()  # Seite/Ordner weg: doch ein Ansichtswechsel,
                st.view_gen += 1        # gesammelte Drehungen bleiben
            return
        if profile.id != st.profile.id:
            self.views[st.profile.id] = (st.workspace_id, self._controls.base_index())
        else:  # dasselbe Profil neu laden: wie bisher zum Heim-Arbeitsbereich
            self.views.pop(profile.id, None)
        self.reset(profile)

    def snapshot(self) -> ViewSnapshot:
        st = self._state
        return (st.profile, st.workspace_id, st.page_index, dict(self.views),
                list(self._folders.levels), st.view_gen)

    def restore(self, snap: ViewSnapshot) -> None:
        st = self._state
        st.profile, st.workspace_id, st.page_index, self.views, levels, st.view_gen = snap
        self._folders.levels = levels

    def remembered_views(self, existing: Iterable[str] | None = None) -> dict:
        """Zuletzt aktive Ansicht je Profil (inkl. der aktuellen), JSON-faehig fuer
        ``settings.last_pages``. Mit ``existing`` (vorhandene Profil-IDs) werden Eintraege
        geloeschter Profile vergessen."""
        if existing is not None:
            keep = set(existing)
            self.views = {pid: v for pid, v in self.views.items() if pid in keep}
        views = dict(self.views)
        st = self._state
        views[st.profile.id] = (st.workspace_id, self._controls.base_index())
        return {pid: {"workspace": ws, "page": page} for pid, (ws, page) in views.items()}

    # --- Abfragen ------------------------------------------------------------------------

    def view_state(self) -> dict:
        """Aktuelle Ansicht als JSON-faehiges dict (API ``view.get``/``view.changed``)."""
        st = self._state
        ws = st.workspace
        return {"profile": st.profile.id, "workspace": st.workspace_id,
                "page": st.page_index, "page_count": len(ws.touch_pages) if ws else 0,
                **self.folder_state(),
                "workspaces": [{"id": w.id, "name": w.name, "pages": len(w.touch_pages)}
                               for w in st.profile.workspaces]}

    def folder_state(self) -> dict:
        """Geoeffneter Ordner (Seiten-ID oder ``None``) und die Seiten-IDs, zu denen „Zurück“
        Ebene fuer Ebene fuehrt, aussen zuerst (``folder_stack``)."""
        top, dyn = self._folders.top, self._dynamic.page()
        if dyn is not None:  # „Zurück“ fuehrt auf die Seite darunter
            under = page_at(self._state.workspace, self._state.page_index)
            return {"folder": dyn.page.id,
                    "folder_stack": self._folders.back_ids() + [under.id if under else ""]}
        return {"folder": top.page if top else None, "folder_stack": self._folders.back_ids()}

    def changed(self) -> None:
        if self._hooks.on_view:
            self._hooks.on_view()

    # --- Navigation (engine_call) --------------------------------------------------------

    def call(self, name: str, params: dict) -> None:
        params = params or {}
        target = self._targets.get(name)
        if target is None:
            log.warning("Unbekanntes Navigationsziel %r", name)
            return
        if name not in PAGE_TARGETS:
            target(params)
            return
        left, gen = self._close_dynamic(), self._state.view_gen
        target(params)
        if left and self._state.view_gen == gen:  # Ziel ungueltig: die Seite darunter zeigen
            self.set_page(self._state.page_index)

    def _step(self, step: int, params: dict) -> None:
        """Naechste/vorige normale Seite (im Ordner: hinaus)."""
        self._show(self._folders.step(self._state.workspace, self._state.page_index, step))

    def _page(self, params: dict) -> None:
        """Seite nach Index (auch eine Ordnerseite)."""
        try:
            index = int(params.get("index", 0))
        except (TypeError, ValueError):
            index = -1
        ws = self._state.workspace
        if page_at(ws, index) is None:
            log.warning("Seite %r gibt es nicht", params.get("index"))
        self._show(self._folders.goto(ws, self._state.page_index, index))

    def _folder(self, params: dict) -> None:
        """Ordnerseite ``page`` oeffnen (mit ``auto_exit``: nach einer Aktion zurueck)."""
        ws, page = self._state.workspace, params.get("page")
        index = find_page(ws, page)
        if index < 0 or not ws.touch_pages[index].folder:
            log.warning("Ordnerseite %r gibt es nicht", page)
            return
        self._show(self._folders.open(ws, self._state.page_index, index,
                                      bool(params.get("auto_exit"))))

    def _dynamic_folder(self, params: dict) -> None:
        left = self._close_dynamic()
        opened = self._dynamic.open(params.get("kind"))
        if opened and self._dynamic.page().encoders is not None:
            self._knobs_reassigned()
        if opened or left:
            self.set_page(self._state.page_index)

    def _open_config(self, params: dict) -> None:
        if self._hooks.on_open_config:
            self._hooks.on_open_config()

    def _profile(self, params: dict) -> None:
        if self._hooks.on_profile:
            self._hooks.on_profile(params.get("id"))
        else:
            log.warning("Profilwechsel nicht verfuegbar: %r", params.get("id"))

    # --- Wechsel -------------------------------------------------------------------------

    def _close_dynamic(self) -> bool:
        """Dynamischen Ordner schliessen; ``True``, wenn einer offen war. Hatte er eigene
        Regler, verfallen deren Leistenwerte."""
        mixer = self._controls.mixer()
        if not self._dynamic.close():
            return False
        if mixer is not None:
            self._knobs_reassigned()
        return True

    def _show(self, index: int | None) -> None:
        if index is not None:
            self.set_page(index)

    def folder_back(self) -> None:
        """Eine Ordnerebene zurueck (ausserhalb eines Ordners: nichts); ein dynamischer
        Ordner zuerst."""
        if self._close_dynamic():
            self.set_page(self._state.page_index)
        else:
            self._show(self._folders.back(self._state.workspace))

    def set_workspace(self, ws_id: object) -> None:
        st = self._state
        if st.find_workspace(ws_id) is None:
            log.warning("Arbeitsbereich %r gibt es nicht", ws_id)
            return
        st.workspace_id = ws_id
        self._folders.clear()
        self._dynamic.close()
        st.page_index = first_normal(st.workspace)
        self._new_view()  # gehaltene hold_key-Aktionen loest das Loslassen (``dispatch``)
        st.feedback.clear()  # Werte und Rad-Bogen gehoerten zum alten Bereich
        self._redraw.now()
        self.changed()

    def set_page(self, index: int) -> None:
        self._state.page_index = index
        self._new_view()
        self._state.feedback.leave_page()
        self._redraw.now()
        self.changed()
