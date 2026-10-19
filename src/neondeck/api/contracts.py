"""Verträge zwischen Dienst, API und Editor (``typing.Protocol``).

* ``EditorBackend``: was das Einstellungsfenster von der Engine braucht. Im Editor-Prozess
  ist das die ``RemoteEngine`` (über die API), in Tests eine lokale ``Engine``.
* ``ServiceLink``: Anfragen an den Dienst (nur mit Dienst; ``RemoteEngine``).
* ``ProfileRepository``: Profilspeicher (``ProfileStore`` im Dienst, ``RemoteStore`` im Editor).
* ``ServiceFacade``: was der ``ApiServer`` vom laufenden Dienst (``App``) braucht.
* ``SettingsControl``: Einstellungen ändern (``service.SettingsController``).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..core.settings import Settings
    from ..device.layout import ControlRef
    from ..device.protocol import Event
    from ..engine import Engine
    from ..profile.model import Profile, Workspace
    from ..profile.store import ProfileStore

# Rückruf einer asynchronen Anfrage: (Ergebnis, Fehlertext | None)
Done = Callable[[Any, str | None], None]


class EditorBackend(Protocol):
    """Ansicht und Bedienung der Engine aus Sicht des Einstellungsfensters (die Ansicht nur
    lesend; sie aendert sich ueber ``set_profile``, ``show_workspace`` und ``show_page``)."""

    @property
    def profile(self) -> Profile: ...

    @property
    def workspace_id(self) -> str | None: ...

    @property
    def page_index(self) -> int: ...

    @property
    def workspace(self) -> Workspace | None: ...

    def set_profile(self, profile: Profile, *, keep_view: bool = False) -> None:
        """Bearbeitetes Profil übernehmen (anzeigen und speichern lassen)."""

    def show_workspace(self, ws_id: str) -> None:
        """Arbeitsbereich ``ws_id`` zeigen (Seite 1)."""

    def show_page(self, index: int) -> None:
        """Seite ``index`` des aktuellen Arbeitsbereichs zeigen."""

    def trigger(self, ref: ControlRef, action: dict | None, *, steps: int = 0) -> None:
        """„Testen“: Aktion einmal auslösen."""

    def handle(self, event: Event) -> None:
        """Modus „Simulieren“: ``event`` wirkt, als käme es vom Gerät."""


class ServiceLink(Protocol):
    """Anfragen an den laufenden Dienst (JSON-API)."""

    def request(self, method: str, params: dict | None = None) -> Any:
        """Blockierend (mit Ereignisschleife); Fehler als ``ApiError``."""

    def request_async(self, method: str, params: dict | None, done: Done) -> None:
        """Nicht blockierend; ``done(ergebnis, fehler)`` im GUI-Thread."""

    def drain(self, timeout: float) -> bool:
        """Auf ausstehende Speicherungen warten; ``False`` nach ``timeout`` Sekunden."""


class ProfileRepository(Protocol):
    """Profile lesen und schreiben; Lesefehler als ``OSError``/``ValueError``."""

    def list(self) -> list[str]: ...
    def load(self, pid: str) -> Profile: ...
    def name(self, pid: str) -> str: ...
    def save(self, profile: Profile) -> None: ...
    def delete(self, pid: str) -> None: ...


class SettingsControl(Protocol):
    """Einstellungen ändern: Werte setzen, wirken lassen (Gerät, Engine, Tray …), speichern."""

    settings: Settings

    def apply(self, changes: Mapping[str, object]) -> None:
        """Geprüfte Werte übernehmen; unbekannte Schlüssel: ``KeyError``."""


class ServiceFacade(Protocol):
    """Der laufende Dienst, wie der ``ApiServer`` ihn sieht (``App``)."""

    engine: Engine
    store: ProfileStore
    settings: Settings
    settings_controller: SettingsControl
    api: Any

    @property
    def dynamic_mode(self) -> bool: ...

    def add_listener(self, fn: Callable[[str, dict], None]) -> None: ...
    def device_status(self) -> dict: ...
    def diag_info(self) -> dict: ...
    def switch_profile(self, pid: str, *, auto: bool = False) -> None: ...
    def open_config(self) -> None: ...
    def start_screensaver(self, name: str | None = None) -> bool: ...
