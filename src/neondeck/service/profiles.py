"""Profilwahl des Dienstes: Startprofil (mit Rueckfall auf das Standardprofil) und Wechsel."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..core.assets import assets_dir
from ..core.i18n import tr
from ..profile.defaults import ensure_default, regenerate_default
from ..profile.model import Profile
from ..profile.store import DEFAULT_ID, ProfileStore

if TYPE_CHECKING:
    from ..core.settings import Settings
    from ..engine import Engine
    from ..engine.dynamic_mode import DynamicMode
    from .tray import Tray

log = logging.getLogger(__name__)


class ProfileSwitcher:
    """``save()`` speichert die Einstellungen, ``emit`` meldet ``profile.changed``; Engine und
    Dynamic Mode kommen mit ``attach`` dazu (das Startprofil braucht sie noch nicht)."""

    def __init__(self, store: ProfileStore, settings: Settings, tray: Tray, *,
                 save: Callable[[], None], emit: Callable[[str, dict], None]) -> None:
        self._store, self._settings, self._tray = store, settings, tray
        self._save, self._emit = save, emit
        self._engine: Engine | None = None
        self._dynamic: DynamicMode | None = None

    def attach(self, engine: Engine, dynamic: DynamicMode) -> None:
        self._engine, self._dynamic = engine, dynamic

    def startup(self) -> Profile:
        """Das zuletzt aktive Profil; fehlt es oder ist es kaputt: das Standardprofil."""
        pid = self._settings.active_profile
        if pid == DEFAULT_ID:
            return self.default()
        if pid not in self._store.list():
            self._tray.notify(tr("Profil '{id}' fehlt – Standardprofil geladen", id=pid), warning=True)
            return self.default()
        profile, err = self._store.load_or_recover(pid)
        if err:
            self._tray.notify(tr("{err} – Standardprofil geladen", err=err), warning=True)
            return self.default()
        return profile

    def default(self) -> Profile:
        """Standardprofil; fehlt es, wird es angelegt, ist es kaputt, neu erzeugt."""
        if DEFAULT_ID not in self._store.list():
            return ensure_default(self._store, assets_dir())
        profile, err = self._store.load_or_recover(DEFAULT_ID)  # kaputt: Sicherungskopie
        if err is None:
            return profile
        profile = regenerate_default(self._store, assets_dir())
        try:
            self._store.load(DEFAULT_ID)
        except Exception:  # noqa: BLE001 - kaputte Vorlage verhindert nie den Start
            self._tray.notify(tr("{err} – Vorlage fehlt, leeres Profil geladen", err=err), warning=True)
        else:
            self._tray.notify(tr("{err} – Standardprofil neu angelegt, Sicherung im Profilordner",
                              err=err),
                              warning=True)
        return profile

    def switch(self, pid: object, *, auto: bool = False) -> None:
        """Profilwechsel (Aktion „Profil“, API, mit ``auto`` der Dynamic Mode); unbekannte
        oder kaputte Profile aendern nichts. Ein Wechsel von Hand pausiert den Dynamic Mode
        bis zum Fokus auf eine andere App."""
        if not isinstance(pid, str) or pid not in self._store.list():
            log.warning("Profil %r gibt es nicht", pid)
            return
        profile, err = self._store.load_or_recover(pid)
        if err:
            self._tray.notify(err, warning=True)
            return
        self._engine.set_profile(profile)
        self._settings.active_profile = pid
        self._save()
        if not auto:
            self._dynamic.on_manual_switch(pid)
        self._tray.notify(tr("Profil „{name}“", name=profile.name or pid), kind="profile")
        self._emit("profile.changed", {"id": pid, "active": pid})
