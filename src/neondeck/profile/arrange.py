"""Arbeitsbereiche und Seiten umsortieren (Dialog „Anordnen …“, verschiebbare Seitenreiter).

* Arbeitsbereiche: Die runden Tasten, die auf einen Arbeitsbereich schalten, folgen der neuen
  Reihenfolge – die Taste mit der kleinsten Nummer bekommt den ersten dieser Arbeitsbereiche
  usw. Andere Belegungen der runden Tasten bleiben, wo sie sind; Arbeitsbereiche ohne Taste
  bekommen keine.
* Seiten: Aktionen ``page`` (Seite per Nummer) im selben Arbeitsbereich zeigen danach auf
  dieselbe Seite wie vorher.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..core.i18n import N_, tr
from ..device.layout import ROUND_CODES
from .action_types import ActionType
from .model import Profile, Workspace
from .walk import iter_steps, iter_workspace_actions


def _same_set(order: list[str], ids: list[str], what: str) -> None:
    if sorted(order) != sorted(ids):
        raise ValueError(tr("Neue Reihenfolge der {what} passt nicht zum Profil", what=tr(what)))


def reorder_workspaces(profile: Profile, order: Iterable[str]) -> None:
    order = list(order)
    by_id = {w.id: w for w in profile.workspaces}
    _same_set(order, list(by_id), N_("Arbeitsbereiche"))
    profile.workspaces = [by_id[i] for i in order]
    keys = [c for c in ROUND_CODES if profile.round.get(c) is not None
            and profile.round[c].action.get("type") == ActionType.WORKSPACE
            and profile.round[c].action.get("id") in by_id]
    if len(keys) < 2:
        return
    rank = {ws_id: n for n, ws_id in enumerate(order)}
    held = sorted((profile.round[c] for c in keys), key=lambda a: rank[a.action["id"]])
    for code, assignment in zip(keys, held):
        profile.round[code] = assignment


def reorder_pages(ws: Workspace, order: Iterable[str]) -> dict[int, int]:
    """Seiten in ``order`` (Seiten-IDs) bringen; liefert alte → neue Nummer."""
    order = list(order)
    _same_set(order, [p.id for p in ws.touch_pages], N_("Seiten"))
    old = {p.id: i for i, p in enumerate(ws.touch_pages)}
    by_id = {p.id: p for p in ws.touch_pages}
    ws.touch_pages = [by_id[i] for i in order]
    moved = {old[pid]: new for new, pid in enumerate(order)}
    for action in iter_workspace_actions(ws):
        for step in iter_steps(action):
            if step.get("type") == ActionType.PAGE and isinstance(step.get("index"), int) \
                    and step["index"] in moved:
                step["index"] = moved[step["index"]]
    return moved
