"""Handler-Gruppen der API (je Gruppe eine Klasse mit ``@api_method``-Methoden).

Alle sehen den Dienst nur ueber die Fassade (``contracts.ServiceFacade``), die erst nach
``ApiServer.attach`` da ist – darum holen sie sie bei jedem Aufruf ueber ``service()``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...engine import Engine
    from ...profile.store import ProfileStore
    from ..contracts import ServiceFacade


class Handlers:
    """Basis: Zugriff auf Fassade, Engine und Profilspeicher des Dienstes."""

    def __init__(self, service: Callable[[], ServiceFacade]) -> None:
        self._service = service

    @property
    def facade(self) -> ServiceFacade:
        return self._service()

    @property
    def engine(self) -> Engine:
        return self._service().engine

    @property
    def store(self) -> ProfileStore:
        return self._service().store
