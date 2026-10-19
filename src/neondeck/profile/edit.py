"""Profil bearbeiten, ohne Qt: was das Einstellungsfenster am Modell aendert.

Belegung an einer Stelle lesen und schreiben (Sticky-Felder: die Sticky-Kachel), Elemente
ablegen, verschieben, tauschen, kopieren, duplizieren und leeren, Sticky-Kacheln, Ordnerseiten,
Seiten anlegen/einfuegen/entfernen/umbenennen/anordnen, Leisten und LED-Farbe eines
Arbeitsbereichs. Die Funktionen aendern das Profil direkt und liefern zurueck, was passiert
ist (oder warum nicht); Meldungen, Speichern und Rückgängig macht das Fenster.

Regeln wie in der Engine: Feld 1 einer Ordnerseite ist „Zurück“ und nicht belegbar,
Sticky-Kacheln gelten nur auf normalen Seiten, die letzte normale Seite bleibt.
"""
from __future__ import annotations

import copy
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from neondeck.device.layout import ROUND_CODES, TOUCH_BUTTONS

from ..core.i18n import tr
from ..device.layout import CONTROL_COUNTS, SQUARE_CODES, ControlKind, ControlRef
from . import arrange
from .ids import new_page_id
from .model import (
    STRIP_LEFT,
    STRIP_MODES,
    Assignment,
    Encoder,
    Profile,
    TouchPage,
    Wheel,
    Workspace,
)
from .walk import iter_assignment_actions, iter_steps

BUTTON_KINDS = frozenset({ControlKind.TOUCH, ControlKind.ROUND, ControlKind.SQUARE})
# Leisten belegt man nicht
COUNTS = {k: n for k, n in CONTROL_COUNTS.items() if k != ControlKind.STRIP}


@dataclass(frozen=True)
class EditContext:
    """Profil, Arbeitsbereich und Seite, zu denen eine Belegung gehoert."""
    profile: Profile
    workspace: Workspace | None
    page: TouchPage | None


@dataclass
class Item:
    """Ein Element mit Wert: woher (Art, Nummer) und sein Wert (Modellobjekt oder None)."""
    kind: str
    index: int
    value: Any


# --- Regeln -------------------------------------------------------------------------------

def is_locked_back(page: TouchPage | None, index: int) -> bool:
    """Feld 0 einer Ordnerseite ist „Zurück“ und nicht belegbar."""
    return page is not None and page.folder and index == 0


def sticky_at(ws: Workspace | None, page: TouchPage | None, index: int) -> Assignment | None:
    """Sticky-Kachel des Arbeitsbereichs auf Feld ``index`` (nur auf normalen Seiten)."""
    if ws is None or page is None or page.folder or not 0 <= index < TOUCH_BUTTONS:
        return None
    return ws.sticky.get(index)


def is_last_normal(ws: Workspace, page: TouchPage) -> bool:
    """``page`` ist die letzte normale Seite (sie darf weder weg noch Ordner werden)."""
    return not page.folder and [p for p in ws.touch_pages if not p.folder] == [page]


def available(ctx: EditContext, ref: ControlRef) -> bool:
    """Gibt es das Element an dieser Stelle (Touch braucht eine Seite, Regler/Rad einen
    Arbeitsbereich)?"""
    if ref.kind == ControlKind.TOUCH:
        return ctx.page is not None
    if ref.kind in (ControlKind.KNOB, ControlKind.WHEEL):
        return ctx.workspace is not None
    return True


def locked(ctx: EditContext, ref: ControlRef) -> bool:
    return ref.kind == ControlKind.TOUCH and is_locked_back(ctx.page, ref.index)


def sticky(ctx: EditContext, ref: ControlRef) -> bool:
    return ref.kind == ControlKind.TOUCH and \
        sticky_at(ctx.workspace, ctx.page, ref.index) is not None


def empty_value(kind: str):
    """Wert eines leeren Elements: Regler und Rad bleiben als leere Objekte."""
    return Encoder() if kind == ControlKind.KNOB else Wheel() if kind == ControlKind.WHEEL else None


def is_empty(kind: str, value) -> bool:
    return value is None or value == empty_value(kind)


# --- Lesen und schreiben ---------------------------------------------------------------

def get_value(ctx: EditContext, ref: ControlRef):
    """Belegung an ``ref``; Touch-Felder mit Sticky-Kachel: die Sticky-Kachel."""
    p, ws, page = ctx.profile, ctx.workspace, ctx.page
    if ref.kind == ControlKind.TOUCH:
        if sticky(ctx, ref):
            return ws.sticky[ref.index]
        return page.buttons[ref.index] if page else None
    if ref.kind == ControlKind.ROUND:
        return p.round.get(ROUND_CODES[ref.index])
    if ref.kind == ControlKind.SQUARE:
        return p.square.get(SQUARE_CODES[ref.index])
    if ref.kind == ControlKind.KNOB:
        return ws.encoders[ref.index] if ws else None
    return ws.wheel if ws else None


def _set_touch(ctx: EditContext, index: int, value) -> None:
    ws, page = ctx.workspace, ctx.page
    if page is None or is_locked_back(page, index):
        return
    if sticky_at(ws, page, index) is None:
        page.buttons[index] = value
    elif value is None:
        del ws.sticky[index]
    else:
        ws.sticky[index] = value


def set_value(ctx: EditContext, ref: ControlRef, value) -> None:
    """Kopie von ``value`` an ``ref`` schreiben (Sticky-Felder: die Sticky-Kachel; leer wird
    bei Regler/Rad ein leeres Objekt)."""
    value = copy.deepcopy(value)
    p, ws = ctx.profile, ctx.workspace
    if ref.kind == ControlKind.TOUCH:
        _set_touch(ctx, ref.index, value)
    elif ref.kind == ControlKind.ROUND:
        p.round[ROUND_CODES[ref.index]] = value
    elif ref.kind == ControlKind.SQUARE:
        p.square[SQUARE_CODES[ref.index]] = value
    elif ref.kind == ControlKind.KNOB and ws:
        ws.encoders[ref.index] = value if value is not None else Encoder()
    elif ref.kind == ControlKind.WHEEL and ws:
        ws.wheel = value if value is not None else Wheel()


def take_items(ctx: EditContext, refs: Iterable[ControlRef]) -> list[Item]:
    """Kopien der Werte an ``refs``, nach Art und Nummer sortiert."""
    refs = sorted(refs, key=lambda r: (r.kind, r.index))
    return [Item(r.kind, r.index, copy.deepcopy(get_value(ctx, r))) for r in refs]


def clear(ctx: EditContext, refs: Iterable[ControlRef]) -> bool:
    """Elemente leeren; ``True``, wenn sich etwas geaendert hat."""
    changed = False
    for ref in refs:
        if not is_empty(ref.kind, get_value(ctx, ref)):
            set_value(ctx, ref, empty_value(ref.kind))
            changed = True
    return changed


# --- Ablegen, Verschieben, Kopieren -------------------------------------------------------

class Refusal(StrEnum):
    """Warum eine Aktion nicht abgelegt wurde."""
    TOUCH_ONLY = "touch_only"    # Anzeige (Uhr, Datum …) nur auf Touch-Tasten
    LOCKED = "locked"            # Feld 1 einer Ordnerseite
    ROTATE_ONLY = "rotate_only"  # Rad: nur Drehaktionen
    PRESS_ONLY = "press_only"    # Tasten: keine Drehaktionen


def dropped_value(ctx: EditContext, ref: ControlRef, action: dict, kinds: Collection[str],
                  touch_only: Collection[str]):
    """Neuer Wert, wenn ``action`` (kann ``kinds``: press/rotate) auf ``ref`` abgelegt wird;
    Regler: Dreh- oder Druckaktion, Taste: Bild bleibt. ``Refusal``, wenn es nicht geht."""
    if action.get("type") in touch_only and ref.kind != ControlKind.TOUCH:
        return Refusal.TOUCH_ONLY
    if locked(ctx, ref):
        return Refusal.LOCKED
    current = copy.deepcopy(get_value(ctx, ref))
    if ref.kind == ControlKind.KNOB:
        enc = current or Encoder()
        if "rotate" in kinds:
            enc.rotate = action
        else:
            enc.press = action
        return enc
    if ref.kind == ControlKind.WHEEL:
        if "rotate" not in kinds:
            return Refusal.ROTATE_ONLY
        wheel = current or Wheel()
        wheel.rotate = action
        return wheel
    if "press" not in kinds:
        return Refusal.PRESS_ONLY
    return Assignment(action, current.image) if current else Assignment(action)


def file_targets(ctx: EditContext, ref: ControlRef) -> list[ControlRef]:
    """Ziele fuer abgelegte Dateien: ``ref``, bei Touch dahinter die freien Felder der Seite."""
    targets = [ref]
    if ref.kind == ControlKind.TOUCH and ctx.page is not None:
        targets += [ControlRef(ControlKind.TOUCH, i) for i in range(ref.index + 1, TOUCH_BUTTONS)
                    if ctx.page.buttons[i] is None
                    and not sticky(ctx, ControlRef(ControlKind.TOUCH, i))]
    return targets


def fit(value, src_kind: str, dst_kind: str, touch_only: Collection[str]) -> tuple[bool, Any]:
    """Wert von ``src_kind`` fuer ``dst_kind`` (``(False, None)``: passt nicht). Tasten
    untereinander tauschbar (Anzeigen ``touch_only`` nur auf Touch), Regler und Rad nur unter
    sich."""
    if src_kind in BUTTON_KINDS and dst_kind in BUTTON_KINDS:
        if dst_kind != ControlKind.TOUCH and value is not None and \
                (value.action or {}).get("type") in touch_only:
            return False, None
        return True, value
    return (src_kind == dst_kind), (value if src_kind == dst_kind else None)


def place_targets(items: list[Item], target: ControlRef) -> list[tuple[Item, ControlRef]]:
    """Ziele beim Einfuegen: Abstaende (Nummern) gelten nur innerhalb einer Art. Abgelegt
    wird die Gruppe der Art von ``target`` (gibt es keine: die der ersten Art), ihr erstes
    Element auf ``target``, die weiteren mit demselben Abstand dahinter. Elemente anderer
    Arten, ueber den Rand fallende und doppelte Ziele entfallen (bleiben, wo sie sind)."""
    if not items:
        return []
    kinds = [i.kind for i in items]
    kind = target.kind if target.kind in kinds else kinds[0]
    group = [i for i in items if i.kind == kind]
    first = min(i.index for i in group)
    out, seen = [], set()
    for item in sorted(group, key=lambda i: i.index):
        dst = ControlRef(target.kind, target.index + item.index - first)
        if 0 <= dst.index < COUNTS.get(target.kind, 0) and dst not in seen:
            seen.add(dst)
            out.append((item, dst))
    return out


@dataclass
class Placed:
    """Ergebnis von ``place``: belegte Ziele, uebersprungene Elemente; ``blocked`` (Ziel,
    Quelle): ein verdraengter Wert passt nicht auf die frei gewordene Quelle, nichts geaendert."""
    placed: list[ControlRef] = field(default_factory=list)
    skipped: int = 0
    blocked: tuple[ControlRef, ControlRef] | None = None


def _swap_back(ctx: EditContext, pairs: list, touch_only: Collection[str]):
    """Beim Verschieben: was an den Zielen lag, rueckt auf die frei gewordenen Quellen.
    Liste ``(Quelle, Wert)`` oder ``(Ziel, Quelle)`` als ``tuple``, wenn es nicht passt."""
    sources = {s for s, _, _ in pairs}
    dests = [d for _, d, _ in pairs]
    displaced = [(d, copy.deepcopy(get_value(ctx, d))) for d in dests if d not in sources]
    freed = [s for s, _, _ in pairs if s not in dests]
    back: list[tuple[ControlRef, object]] = []
    for src, (d, old) in zip(freed, displaced):
        ok, value = fit(old, d.kind, src.kind, touch_only)
        if not ok and not is_empty(d.kind, old):
            return d, src
        back.append((src, value if ok else empty_value(src.kind)))
    back += [(src, empty_value(src.kind)) for src in freed[len(displaced):]]
    return back


def place(ctx: EditContext, items: list[Item], target: ControlRef, *,
          touch_only: Collection[str], move: bool = False) -> Placed:
    """Elemente ab ``target`` ablegen. ``move``: die Quellen werden frei; was an den Zielen
    lag, rueckt auf die frei gewordenen Quellen (ein Element: Tausch). Kann ein verdraengter
    Wert dort nicht hin (z. B. Uhr auf eine runde Taste), passiert nichts."""
    targets = place_targets(items, target)
    pairs, skipped = [], len(items) - len(targets)
    for item, dst in targets:
        ok, value = fit(item.value, item.kind, dst.kind, touch_only)
        if ok and not locked(ctx, dst):
            pairs.append((ControlRef(item.kind, item.index), dst, value))
        else:
            skipped += 1
    back: list = []
    if move:
        pairs = [(s, d, v) for s, d, v in pairs if s != d]
        back = _swap_back(ctx, pairs, touch_only)  # erst pruefen, dann aendern
        if isinstance(back, tuple):
            return Placed(blocked=back)
    for _, dst, value in pairs:
        set_value(ctx, dst, value)
    for src, value in back:
        set_value(ctx, src, value)
    return Placed([d for _, d, _ in pairs], skipped)


def duplicate(ctx: EditContext, items: list[Item]) -> tuple[list[ControlRef], int]:
    """Belegte Elemente auf den naechsten freien Platz derselben Art dahinter; belegte Ziele
    und Zahl der Elemente ohne freien Platz."""
    placed, missing = [], 0
    for item in items:
        if is_empty(item.kind, item.value):
            continue
        free = next((i for i in range(item.index + 1, COUNTS[item.kind])
                     if is_empty(item.kind, get_value(ctx, ControlRef(item.kind, i)))
                     and not locked(ctx, ControlRef(item.kind, i))), None)
        if free is None:
            missing += 1
            continue
        ref = ControlRef(item.kind, free)
        set_value(ctx, ref, item.value)
        placed.append(ref)
    return placed, missing


# --- Sticky und Ordner --------------------------------------------------------------------

@dataclass(frozen=True)
class StickyChange:
    pinned: bool                 # jetzt angeheftet (sonst geloest)
    page_kept_own: bool = False  # geloest, aber die Seite hatte dort schon eine eigene Belegung


def toggle_sticky(ctx: EditContext, index: int) -> StickyChange | None:
    """Touch-Feld ``index`` auf allen (normalen) Seiten des Arbeitsbereichs anheften bzw.
    loesen (dann liegt die Belegung wieder auf der gezeigten Seite, wenn dort frei);
    ``None``: nichts zu tun."""
    ws, page = ctx.workspace, ctx.page
    if ws is None or page is None or page.folder:
        return None
    if index in ws.sticky:
        a = ws.sticky.pop(index)
        own = page.buttons[index] is not None
        if not own:
            page.buttons[index] = a
        return StickyChange(pinned=False, page_kept_own=own)
    a = page.buttons[index]
    if a is None:
        return None
    ws.sticky[index] = a
    page.buttons[index] = None
    return StickyChange(pinned=True)


def toggle_folder(ws: Workspace, index: int) -> bool | None:
    """Seite ``index`` wird Ordnerseite bzw. wieder normal; neuer Zustand (``None``: die
    letzte normale Seite kann kein Ordner werden)."""
    page = ws.touch_pages[index]
    if is_last_normal(ws, page):
        return None
    page.folder = not page.folder
    return page.folder


def drop_missing_folders(page: TouchPage, folder_ids: set) -> int:
    """Ordner-Aktionen der Seite (auch Schritte in Makros), deren Ordnerseite es im
    Ziel-Arbeitsbereich nicht gibt, verlieren ihr Ziel (statt auf eine fremde Seite zu
    zeigen); Anzahl."""
    lost = 0
    for a in page.buttons:
        if a is None:
            continue
        for action in iter_assignment_actions(a):
            for step in iter_steps(action):
                if step.get("type") == "folder" and step.get("page") is not None \
                        and step.get("page") not in folder_ids:
                    del step["page"]
                    lost += 1
    return lost


# --- Seiten -----------------------------------------------------------------------------

def new_page_id_for(ws: Workspace) -> str:
    return new_page_id({p.id for p in ws.touch_pages}, len(ws.touch_pages) + 1)


def page_index(ws: Workspace, page_id: str) -> int:
    """Nummer der Seite mit ``page_id`` (-1: gibt es nicht)."""
    return next((i for i, p in enumerate(ws.touch_pages) if p.id == page_id), -1)


def add_page(ws: Workspace) -> int:
    """Leere Seite hinten anhaengen; ihre Nummer."""
    ws.touch_pages.append(TouchPage(new_page_id_for(ws), tr("Seite {n}", n=len(ws.touch_pages) + 1)))
    return len(ws.touch_pages) - 1


def paste_page(ws: Workspace, page: TouchPage, at: int) -> int:
    """Kopierte Seite an Stelle ``at`` einfuegen (neue Kennung, kein Ordner-Elternteil);
    Zahl der Ordner-Tasten, deren Ordnerseite es hier nicht gibt (Ziel entfernt)."""
    page.id = new_page_id_for(ws)
    page.parent = None
    lost = drop_missing_folders(page, {p.id for p in ws.touch_pages if p.folder})
    ws.touch_pages.insert(at, page)
    return lost


def remove_page(ws: Workspace, page: TouchPage) -> bool:
    """Seite entfernen (``False``: die letzte normale Seite bleibt)."""
    if is_last_normal(ws, page):
        return False
    ws.touch_pages.remove(page)
    return True


def rename_page(page: TouchPage, name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    page.name = name
    return True


def moved_order(ws: Workspace, src: int, dst: int) -> list[str] | None:
    """Seiten-IDs, wenn Seite ``src`` an Stelle ``dst`` rueckt (``None``: ungueltig)."""
    n = len(ws.touch_pages)
    if not (0 <= src < n and 0 <= dst < n):
        return None
    order = [p.id for p in ws.touch_pages]
    order.insert(dst, order.pop(src))
    return order


def apply_arrangement(profile: Profile, workspace_order: list[str] | None,
                      page_orders: dict[str, list[str]]) -> bool:
    """Neue Reihenfolge der Arbeitsbereiche und Seiten; ``True``, wenn sich etwas geaendert
    hat. Passt sie nicht zum Profil: ``ValueError``, das Profil bleibt unveraendert."""
    before = profile.to_json()
    try:
        if workspace_order is not None:
            arrange.reorder_workspaces(profile, workspace_order)
        for w in profile.workspaces:
            if w.id in page_orders:
                arrange.reorder_pages(w, page_orders[w.id])
    except ValueError:
        profile.replace_with(Profile.from_json(before))
        raise
    return profile.to_json() != before


# --- Arbeitsbereich ---------------------------------------------------------------------

def set_strip_mode(ws: Workspace, side: str, mode: str) -> bool:
    """Anzeige der linken/rechten Leiste (Regler oder Systemlast); ``True`` bei Aenderung."""
    if mode not in STRIP_MODES or ws.strip_mode(side) == mode:
        return False
    if side == STRIP_LEFT:
        ws.strip_left = mode
    else:
        ws.strip_right = mode
    return True


def set_led_color(ws: Workspace, color: str | None) -> bool:
    if ws.led_color == color:
        return False
    ws.led_color = color
    return True
