"""Profile durchlaufen: Profil-JSON (verschachtelte dicts/Listen) und Aktionen am Modell.

Ein Ort fuer die Walker, die Freigeben (Bildverweise), Vorlagen (Ziele umbiegen), Anordnen
(Seitennummern) und Einfuegen (Ordnerziele) brauchen. ``iter_steps`` laeuft auch in die
Schritte von Makros.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from .model import Assignment, Workspace


def iter_dicts(node: Any) -> Iterator[dict]:
    """Jedes dict im JSON-Baum, Eltern vor Kindern (Werte duerfen unterwegs ersetzt werden,
    solange sich die Schluessel nicht aendern)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_dicts(v)


def rewrite_values(node: Any, key: str, fn: Callable[[str], str]) -> None:
    """Jeden Text unter Schluessel ``key`` im JSON-Baum durch ``fn(text)`` ersetzen."""
    if isinstance(node, dict):
        for k, value in node.items():
            if k == key and isinstance(value, str):
                node[k] = fn(value)
            else:
                rewrite_values(value, key, fn)
    elif isinstance(node, list):
        for item in node:
            rewrite_values(item, key, fn)


def iter_steps(action: Any) -> Iterator[dict]:
    """Die Aktion selbst und (rekursiv) die Schritte eines Makros; Nicht-dicts nichts."""
    if isinstance(action, dict):
        yield action
        for step in action.get("steps") or []:
            yield from iter_steps(step)


def iter_assignment_actions(a: Assignment) -> Iterator[Any]:
    """Aktionen einer Belegung: Tippen, Doppeltippen, Halten, dann die Zustaende (auch None)."""
    yield from (a.action, a.double, a.hold)
    for s in a.states:
        yield s.action


def iter_workspace_actions(ws: Workspace) -> Iterator[Any]:
    """Alle Aktionen eines Arbeitsbereichs: Seiten, Sticky-Felder, Regler (samt Ebenen), Rad."""
    for page in ws.touch_pages:
        for a in page.buttons:
            if a is not None:
                yield from iter_assignment_actions(a)
    for a in ws.sticky.values():
        yield from iter_assignment_actions(a)
    for e in ws.encoders:
        yield from (e.rotate, e.press, e.left, e.right, e.tap)
        for layer in e.layers:
            yield from (layer.rotate, layer.press, layer.left, layer.right)
    yield from (ws.wheel.rotate, ws.wheel.left, ws.wheel.right, ws.wheel.tap)
