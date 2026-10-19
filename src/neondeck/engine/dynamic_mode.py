"""Dynamic Mode: das Profil folgt dem aktiven Fenster.

Regeln (Entwurf Phase 3, „Fenster & Dynamic Mode“):

* Ein Profil, dessen ``app_ids`` den ``desktopFileName`` oder die ``resourceClass`` des
  Fensters enthaelt (Gross/klein egal), wird aktiviert; passt das aktive Profil selbst, bleibt
  es. Profile mit ``dynamic=False`` werden nie automatisch aktiviert.
* Kein Treffer: Standardprofil – ausser das aktive Profil ist „haltend“ (``hold_profile``).
* Ein manueller Profilwechsel pausiert die Automatik, bis eine *andere* App den Fokus bekommt.
* Global aus (``enabled = False``): nichts.
* Fenster der Arbeitsoberflaeche (plasmashell, KRunner), KWin-interne Fenster ohne
  ``resourceClass`` und der eigene Editor wechseln nie das Profil und beenden auch keine
  Pause (Controller-Entscheid R20).
* Entprellung: erst wenn 150 ms lang kein weiterer Fensterwechsel kam, wird das zuletzt
  aktive Fenster ausgewertet – hoechstens ein Profilwechsel je 150 ms, kein Flackern.

Ohne Qt; Zeit und Zeitgeber kommen von aussen (``clock``, ``call_later``).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..core.values import EPS
from ..core.windows import WindowInfo
from ..profile.store import DEFAULT_ID, ProfileStore

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.15
# Kennungen (desktopFileName oder resourceClass), deren Fenster das Profil nie wechseln
DEFAULT_IGNORE = ("org.kde.plasmashell", "plasmashell", "org.kde.krunner", "krunner",
                  "neondeck-ct")


@dataclass(frozen=True)
class _Meta:
    app_ids: tuple[str, ...]
    dynamic: bool
    hold: bool


class DynamicMode:
    def __init__(self, store: ProfileStore, activate: Callable[[str], None],
                 clock: Callable[[], float] = time.monotonic, *,
                 call_later: Callable[[float, Callable[[], None]], None],
                 current: Callable[[], str], ignore: Iterable[str] = DEFAULT_IGNORE,
                 default_id: str = DEFAULT_ID) -> None:
        self.enabled = True
        self._store = store
        self._activate = activate
        self._clock = clock
        self._call_later = call_later
        self._current = current
        self._ignore = frozenset(i.lower() for i in ignore)
        self._default_id = default_id
        self._pending: WindowInfo | None = None
        self._last_event = 0.0
        self._scheduled = False
        self._app: str | None = None       # App des zuletzt ausgewerteten Fensters
        self._paused = False
        self._paused_app: str | None = None
        self._cache: dict[str, tuple[int, int, _Meta | None]] = {}

    # --- Eingaenge -----------------------------------------------------------------------

    def on_window(self, info: WindowInfo) -> None:
        """Ein Fenster wurde aktiv (direkt aus dem KWin-Waechter, ungefiltert)."""
        if not self.enabled or self._ignored(info):
            return  # Profil bleibt; auch eine Pause nach Handwechsel laeuft weiter
        self._pending = info
        self._last_event = self._clock()
        if not self._scheduled:
            self._scheduled = True
            self._call_later(DEBOUNCE_S, self._flush)

    def _ignored(self, info: WindowInfo) -> bool:
        if not info.resource_class:
            return True  # KWin-interne Fenster
        return (info.desktop_file.lower() in self._ignore
                or info.resource_class.lower() in self._ignore)

    def on_manual_switch(self, profile_id: str) -> None:
        """Profil wurde von Hand gewaehlt: Automatik ruht bis zur naechsten anderen App."""
        self._paused = True
        self._paused_app = self._pending.app_key if self._pending else self._app
        log.debug("Dynamic Mode pausiert (Profil %s von Hand, App %s)", profile_id,
                  self._paused_app)

    # --- Auswertung ----------------------------------------------------------------------

    def _flush(self) -> None:
        self._scheduled = False
        wait = self._last_event + DEBOUNCE_S - self._clock()
        if wait > EPS:  # inzwischen kam ein weiteres Fenster: Ruhe abwarten
            self._scheduled = True
            self._call_later(wait, self._flush)
            return
        info, self._pending = self._pending, None
        if info is None or not self.enabled:
            return
        try:
            self._apply(info)
        except Exception:
            log.exception("Dynamic Mode: Fenster %s nicht ausgewertet", info.app_key)

    def _apply(self, info: WindowInfo) -> None:
        app = info.app_key
        self._app = app
        if self._paused:
            if app == self._paused_app:
                return
            self._paused = False
        target = self._target(info)
        if target is None or target == self._current():
            return
        log.info("Dynamic Mode: Profil %s (Fenster %s)", target, app)
        self._activate(target)

    def _target(self, info: WindowInfo) -> str | None:
        """Profil fuer ``info``; ``None`` = aktives Profil behalten (haltend)."""
        profiles = self._profiles()
        current = self._current()
        hits = [pid for pid, m in profiles.items()
                if m.dynamic and any(info.matches(a) for a in m.app_ids)]
        if hits:
            return current if current in hits else hits[0]
        meta = profiles.get(current)
        if meta is not None and meta.hold:
            return None
        return self._default_id

    def _profiles(self) -> dict[str, _Meta]:
        """Kennungen der Profile; Dateien werden nur bei Aenderung neu gelesen."""
        out: dict[str, _Meta] = {}
        seen = set()
        for pid in self._store.list():
            try:
                st = self._store.path(pid).stat()
            except OSError:
                continue
            seen.add(pid)
            cached = self._cache.get(pid)
            if cached is None or cached[:2] != (st.st_mtime_ns, st.st_size):
                cached = (st.st_mtime_ns, st.st_size, self._read(pid))
                self._cache[pid] = cached
            if cached[2] is not None:
                out[pid] = cached[2]
        for pid in set(self._cache) - seen:
            del self._cache[pid]
        return out

    def _read(self, pid: str) -> _Meta | None:
        try:
            p = self._store.load(pid)
        except Exception as e:  # noqa: BLE001 - kaputte Datei: Profil einfach auslassen
            log.debug("Dynamic Mode: Profil %s nicht lesbar: %s", pid, e)
            return None
        return _Meta(tuple(p.app_ids), p.dynamic, p.hold_profile)
