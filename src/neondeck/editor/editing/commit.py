"""Aenderungen gebuendelt speichern: das Fenster aendert das Profil sofort, gespeichert und am
Geraet gezeigt wird kurz danach (``COMMIT_DELAY_MS``), damit nicht jeder Tastendruck eine
Datei schreibt."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from ...core.i18n import tr
from ...profile.model import Profile
from .history import ProfileHistory

if TYPE_CHECKING:
    from ...api.contracts import EditorBackend, ProfileRepository

log = logging.getLogger(__name__)

COMMIT_DELAY_MS = 300   # Aenderungen buendeln, dann speichern + Geraet neu zeichnen


class CommitScheduler(QObject):
    """Merkt das ausstehende Profil, schreibt den Rückgängig-Schritt und speichert nach
    ``COMMIT_DELAY_MS`` (oder bei ``flush``); ``say`` zeigt Fehler in der Statuszeile."""

    def __init__(self, store: ProfileRepository, engine: EditorBackend,
                 history: ProfileHistory, say: Callable[[str], None],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._engine = engine
        self._history = history
        self._say = say
        self._pending: Profile | None = None  # Profil mit noch nicht gespeicherten Aenderungen
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    def waiting(self) -> bool:
        """Liegt eine Aenderung noch im Puffer (Zeitgeber laeuft)?"""
        return self._timer.isActive()

    def schedule(self, profile: Profile, *, label: str | None = None, merge=None,
                 record: bool = True) -> None:
        """Aenderung an ``profile`` vormerken; ``record``: als Rückgängig-Schritt ``label``
        (nur fuer das Profil, das die Engine zeigt). Gleicher ``merge``-Schluessel wie der
        letzte Schritt: ein Schritt."""
        if self._pending is not None and self._pending is not profile:
            self.flush()  # anderes Profil ausstehend: erst das speichern
        if record and profile is self._engine.profile:
            self._history.record(profile, label or tr("Bearbeiten"), merge)
        self._pending = profile
        self._timer.start(COMMIT_DELAY_MS)

    def commit_now(self, profile: Profile, label: str | None = None) -> None:
        self.schedule(profile, label=label or tr("Profil bearbeiten"))
        self.flush()

    def flush(self) -> None:
        """Ausstehende Aenderungen speichern und am Geraet anzeigen (Seite bleibt).

        Laeuft auch im Timer-Slot: wirft nie. Scheitert das Speichern, bleibt die Aenderung
        ausstehend und der naechste ``flush`` (naechste Aenderung, Schliessen) versucht es neu.
        """
        self._timer.stop()
        profile = self._pending
        if profile is None:
            return
        try:
            self._store.save(profile)
        except Exception as e:  # noqa: BLE001 - nie bis in die Qt-Ereignisschleife
            log.error("Profil %s nicht gespeichert: %s", profile.id, e)
            self._say(tr("Speichern fehlgeschlagen: {error}", error=e))
        else:
            self._pending = None
        if self._engine.profile is profile:
            try:
                self._engine.set_profile(profile, keep_view=True)
            except Exception:
                log.exception("Profil %s nicht am Gerät angezeigt", profile.id)
