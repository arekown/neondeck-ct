"""Was die Bearbeitungs-Controller (``controls``, ``pages``, ``navigation``, ``undoing``,
``windows.extras``) vom Einstellungsfenster brauchen – nur diese Schnittstelle, kein Zugriff
auf seine Interna."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from ...api.contracts import EditorBackend, ProfileRepository, ServiceLink
    from ...device.layout import ControlRef
    from ...profile.edit import EditContext
    from ...profile.model import Profile


class EditView(Protocol):
    engine: EditorBackend
    store: ProfileRepository
    service: ServiceLink | None
    selected: ControlRef | None  # zuletzt gewaehltes Element

    @property
    def profile(self) -> Profile: ...

    def shown_ctx(self) -> EditContext:
        """Die Stelle, die das Fenster zeigt (Klicks und Ablegen beziehen sich darauf)."""

    def selected_refs(self) -> list[ControlRef]:
        """Gewaehlte, belegbare Elemente an der gezeigten Stelle."""

    def finish(self, ctx: EditContext, label: str, select: list[ControlRef] | None = None, *,
               current: ControlRef | None = None, now: bool = False) -> None:
        """Nach einer Aenderung an Elementen: neuer Rückgängig-Schritt ``label``, neu zeichnen,
        vormerken (``now``: gleich speichern), Auswahl ``select`` (``current`` bzw. das
        letzte davon ist das gewaehlte Element)."""

    def say(self, text: str, long: bool = False) -> None:
        """Meldung in der Statuszeile."""

    def sync_from_engine(self, force: bool = False) -> None: ...
    def reload_profiles(self) -> None: ...

    def profile_name(self, pid: str) -> str:
        """Name aus der Profilauswahl (sonst die Kennung)."""

    def dialog_parent(self) -> QWidget: ...
