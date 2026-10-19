"""Seitenauswahl und Ordner eines Arbeitsbereichs, ohne Qt.

* Ordnerseiten (``TouchPage.folder``) gehoeren nicht zum Seitenwechsel, zum Wischen und zu
  den Seitenpunkten; geoeffnet werden sie mit der Aktion ``folder`` (oder ``page`` mit ihrem
  Index), Kachel 0 ist dort immer „Zurück“.
* Ordner lassen sich verschachteln (bis ``MAX_DEPTH`` Ebenen). Jede Ebene merkt sich die
  Seite, zu der „Zurück“ fuehrt, und ob sie nach einer erfolgreich ausgefuehrten Aktion von
  selbst zurueckkehrt (``auto_exit``).
* Seiten werden ueber ihre ID gemerkt: Fuegt der Editor davor eine Seite ein, bleibt der
  Ordner offen (``FolderStack.resolve``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..core.i18n import N_
from ..profile.edit import is_locked_back, sticky_at
from ..profile.model import Assignment, ButtonImage, TouchPage, Workspace

MAX_DEPTH = 8
# Kachel 0 jeder Ordnerseite (fest, damit laufende Gesten sie wiedererkennen)
BACK_TEXT = N_("Zurück")  # nur Anzeige: erkannt wird die Kachel an ``BACK_TILE`` (Identitaet)
BACK_TILE = Assignment({"type": "folder_back"}, ButtonImage(bg="#202020", text=BACK_TEXT))

log = logging.getLogger(__name__)


@dataclass(eq=False)
class FolderLevel:
    """Eine geoeffnete Ordnerebene. Verglichen wird nach Identitaet: ein spaetes Ergebnis
    (Auto-Exit) gehoert genau zu der Ebene, in der die Aktion ausgeloest wurde."""
    page: str               # ID der Ordnerseite
    back: str               # ID der Seite, zu der „Zurück“ fuehrt
    auto_exit: bool = False


class FolderStack:
    """Geoeffnete Ordner, aussen zuerst; leer = normale Seite."""

    def __init__(self) -> None:
        self.levels: list[FolderLevel] = []

    def __bool__(self) -> bool:
        return bool(self.levels)

    def __len__(self) -> int:
        return len(self.levels)

    @property
    def top(self) -> FolderLevel | None:
        return self.levels[-1] if self.levels else None

    @property
    def base(self) -> str | None:
        """Die normale Seite, von der aus der aeusserste Ordner geoeffnet wurde."""
        return self.levels[0].back if self.levels else None

    def push(self, level: FolderLevel) -> bool:
        """Ordner oeffnen; ``False`` bei ``MAX_DEPTH`` offenen Ebenen."""
        if len(self.levels) >= MAX_DEPTH:
            return False
        self.levels.append(level)
        return True

    def pop(self) -> FolderLevel | None:
        return self.levels.pop() if self.levels else None

    def clear(self) -> None:
        self.levels.clear()

    def back_ids(self) -> list[str]:
        """Seiten-IDs der Ruecksprungziele, aussen zuerst (API ``folder_stack``)."""
        return [lvl.back for lvl in self.levels]

    def resolve(self, ws: Workspace | None) -> int | None:
        """Index der innersten Ordnerseite in ``ws``, wenn alle Ebenen dort noch gueltig
        sind (Ordnerseiten noch Ordner, Ausgangsseite noch normal); sonst ``None``."""
        if ws is None or not self.levels:
            return None
        base = find_page(ws, self.levels[0].back)
        if base < 0 or ws.touch_pages[base].folder:
            return None
        index = -1
        for lvl in self.levels:
            index = find_page(ws, lvl.page)
            if index < 0 or not ws.touch_pages[index].folder:
                return None
            if lvl is not self.levels[0] and find_page(ws, lvl.back) < 0:
                return None
        return index

    # --- Navigation: neue Seite (Index) oder ``None`` = bleibt; der Stapel folgt ----------

    def base_index(self, ws: Workspace | None, current: int) -> int:
        """Die normale Seite der Ansicht: im Ordner die, von der er geoeffnet wurde."""
        if not self.levels:
            return current
        index = find_page(ws, self.base)
        return index if index >= 0 else first_normal(ws)

    def open(self, ws: Workspace | None, current: int, target: int,
             auto_exit: bool = False) -> int | None:
        """Ordnerseite ``target`` von Seite ``current`` aus oeffnen (eine Ebene tiefer)."""
        here, folder = page_at(ws, current), page_at(ws, target)
        if here is None or folder is None or not folder.folder:
            return None
        if not self.push(FolderLevel(folder.id, here.id, auto_exit)):
            log.warning("Ordner %r nicht geoeffnet: schon %d Ebenen", folder.id, len(self))
            return None
        return target

    def back(self, ws: Workspace | None) -> int | None:
        """Eine Ebene zurueck (ausserhalb eines Ordners: ``None``)."""
        level = self.pop()
        if level is None:
            return None
        index = find_page(ws, level.back)
        if index < 0:  # Ausgangsseite inzwischen weg: ganz hinaus
            self.clear()
            index = first_normal(ws)
        return index

    def step(self, ws: Workspace | None, current: int, step: int) -> int | None:
        """Naechste/vorige normale Seite; aus einem Ordner heraus von seiner Ausgangsseite
        aus (der Ordner wird verlassen)."""
        target = step_normal(ws, self.base_index(ws, current), step)
        if target is not None:
            self.clear()
        return target

    def goto(self, ws: Workspace | None, current: int, index: int) -> int | None:
        """Seite ``index`` zeigen: eine normale schliesst alle Ordner, eine Ordnerseite wird
        geoeffnet (ist sie schon offen: zurueck bis zu ihrer Ebene). ``None``, wenn es die Seite
        nicht gibt."""
        page = page_at(ws, index)
        if page is None:
            return None
        if not page.folder:
            self.clear()
            return index
        for depth, lvl in enumerate(self.levels):
            if lvl.page == page.id:  # schon offen: bis zu dieser Ebene zurueck
                del self.levels[depth + 1:]
                return index
        return self.open(ws, current, index)

    def keep(self, ws: Workspace, current: int) -> int:
        """Nach dem Bearbeiten des Profils: offener Ordner bleibt offen, solange es ihn (und
        seine Ausgangsseiten) noch gibt; sonst zurueck zur Ausgangsseite bzw. einer normalen
        Seite."""
        if self.levels:
            index = self.resolve(ws)
            if index is not None:
                return index
            base = find_page(ws, self.base)
            self.clear()
            current = base if base >= 0 else current
        current = max(0, min(current, len(ws.touch_pages) - 1))
        page = page_at(ws, current)
        return first_normal(ws) if page is not None and page.folder else current


def page_at(ws: Workspace | None, index: int) -> TouchPage | None:
    if ws and 0 <= index < len(ws.touch_pages):
        return ws.touch_pages[index]
    return None


def find_page(ws: Workspace | None, page_id) -> int:
    """Index der Seite mit ID ``page_id``; -1, wenn es sie nicht gibt."""
    if ws is None or not isinstance(page_id, str):
        return -1
    return next((i for i, p in enumerate(ws.touch_pages) if p.id == page_id), -1)


def normal_pages(ws: Workspace | None) -> list[int]:
    """Indizes der Seiten, die zum Seitenwechsel gehoeren (keine Ordner)."""
    return [i for i, p in enumerate(ws.touch_pages) if not p.folder] if ws else []


def first_normal(ws: Workspace | None) -> int:
    """Erste normale Seite (gibt es keine: 0)."""
    pages = normal_pages(ws)
    return pages[0] if pages else 0


def step_normal(ws: Workspace | None, index: int, step: int) -> int | None:
    """Naechste/vorige normale Seite von ``index`` aus, im Kreis; ``None`` ohne Seiten."""
    pages = normal_pages(ws)
    if not pages:
        return None
    if index in pages:
        return pages[(pages.index(index) + step) % len(pages)]
    # von einer Ordnerseite ohne Ausgangsseite: erste normale Seite in Schrittrichtung
    later = [i for i in pages if (i > index if step > 0 else i < index)]
    if later:
        return later[0] if step > 0 else later[-1]
    return pages[0] if step > 0 else pages[-1]


def page_dots(ws: Workspace | None, index: int) -> tuple[int, int]:
    """(Position, Anzahl) fuer die Seitenpunkte; in einem Ordner keine Punkte."""
    page = page_at(ws, index)
    if page is None or page.folder:
        return 0, 0
    pages = normal_pages(ws)
    return pages.index(index), len(pages)


# --- Was ein Touch-Feld zeigt (Engine, Geraeteansicht und Editor gleich; die Regeln dazu
# stehen in ``profile.edit``) --------------------------------------------------------------

def is_sticky(ws: Workspace | None, page: TouchPage | None, index: int) -> bool:
    return sticky_at(ws, page, index) is not None


def shown_assignment(ws: Workspace | None, page: TouchPage | None,
                     index: int) -> Assignment | None:
    """Was Feld ``index`` zeigt: im Ordner Feld 0 „Zurück“ (``BACK_TILE``), auf normalen
    Seiten die Sticky-Kachel, sonst die Belegung der Seite."""
    if page is None:
        return None
    if is_locked_back(page, index):
        return BACK_TILE
    sticky = sticky_at(ws, page, index)
    if sticky is not None:
        return sticky
    return page.buttons[index] if 0 <= index < len(page.buttons) else None
