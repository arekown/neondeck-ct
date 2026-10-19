"""Mitgelieferte CT-Vorlagen (``data/templates/*.json``, Profil-JSON Version 2).

Jede Vorlage ist ein vollstaendiges Profil mit zusaetzlichem Feld ``description``. Symbole
verweisen auf die importierten Loupedeck-Symbole (``svg:icons/…``); fehlen die, zeigen die
Tasten ihren Text. „Uebernehmen“ legt ein **neues** Profil mit eigener Kennung an
(``instantiate``); „Einfuegen“ haengt die Arbeitsbereiche einer oder mehrerer Vorlagen an ein
bestehendes Profil an (``insert_into``), oder nur ihre Seiten an einen Arbeitsbereich
(``insert_pages``). Die Vorlage selbst wird nie veraendert.

Die Texte der Vorlagen sind deutsch; beim Auflisten und Einfuegen uebersetzt sie ``tr()``
(``template_texts`` nennt die Felder, ``tools/i18n.py`` zieht dieselben heraus).
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..core import paths
from ..core.fileio import read_json
from ..core.i18n import tr
from ..core.values import join_errors
from ..device.layout import ROUND_CODES
from .action_types import ActionType
from .ids import new_page_id, new_uuid_id
from .model import Assignment, Profile, TouchPage, Workspace, validate_profile_json
from .walk import iter_dicts


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    name: str
    description: str


def _dicts(value) -> list[dict]:
    return [d for d in value if isinstance(d, dict)] if isinstance(value, list) else []


def _texts(node, keys: tuple[str, ...]) -> Iterator[tuple[dict, str]]:
    """``(node, key)`` fuer jeden Anzeigetext mit Buchstaben (``"1"``, ``"+"`` bleiben)."""
    if not isinstance(node, dict):
        return
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and any(c.isalpha() for c in value):
            yield node, key


def template_texts(data: dict) -> Iterator[tuple[dict, str]]:
    """``(objekt, schluessel)`` jedes Anzeigetexts einer Vorlage: Name und Beschreibung,
    Namen der Arbeitsbereiche und Seiten, Tastentexte (auch je Zustand), Beschriftungen von
    Reglern und Rad. Aktionen (getippter Text, Kuerzel) zaehlen nicht."""
    yield from _texts(data, ("name", "description"))
    for ws in _dicts(data.get("workspaces")):
        yield from _texts(ws, ("name",))
        yield from _texts(ws.get("wheel"), ("label",))
        for enc in _dicts(ws.get("encoders")):
            yield from _texts(enc, ("label",))
        for page in _dicts(ws.get("touch_pages")):
            yield from _texts(page, ("name",))
            for button in _dicts(page.get("buttons")):
                yield from _texts(button.get("image"), ("text",))
                for state in _dicts(button.get("states")):
                    yield from _texts(state.get("image"), ("text",))


def _translated(data: dict) -> dict:
    """Anzeigetexte der Vorlage in der eingestellten Sprache (aendert ``data``)."""
    for node, key in list(template_texts(data)):
        node[key] = tr(node[key])
    return data


def templates_dir() -> Path:
    return paths.bundled_dir() / "templates"


def _path(template_id: str) -> Path:
    if not template_id or "/" in template_id or template_id.startswith("."):
        raise ValueError(tr("Vorlage {id!r} gibt es nicht", id=template_id))
    return templates_dir() / f"{template_id}.json"


def load_template(template_id: str) -> dict:
    """Profil-JSON der Vorlage (mit ``description``); ``ValueError``, wenn es sie nicht gibt."""
    try:
        data = read_json(_path(template_id))
    except FileNotFoundError:
        raise ValueError(tr("Vorlage {id!r} gibt es nicht", id=template_id)) from None
    if not isinstance(data, dict):
        raise ValueError(tr("Vorlage {id!r} ist kein Profil", id=template_id))
    return data


def list_templates() -> list[TemplateInfo]:
    """Alle lesbaren Vorlagen, nach Name sortiert."""
    out = []
    folder = templates_dir()
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = load_template(path.stem)
        except (OSError, ValueError):
            continue
        out.append(TemplateInfo(path.stem, tr(str(data.get("name") or path.stem)),
                                tr(str(data.get("description") or ""))))
    return sorted(out, key=lambda t: t.name.casefold())


@dataclass(frozen=True)
class Inserted:
    workspace_id: str
    name: str
    round_code: int | None  # runde Taste, die dorthin schaltet (None: keine mehr frei)


def _valid(template_id: str) -> dict:
    data = load_template(template_id)
    data.pop("description", None)
    errors = validate_profile_json(data)
    if errors:
        raise ValueError(tr("Vorlage {id!r} ist ungültig: {errors}", id=template_id,
                            errors=join_errors(errors, 5)))
    return _translated(data)


def _retarget(node, ids: dict[str, str]) -> None:
    """Arbeitsbereich-Aktionen der Vorlage auf die neuen Kennungen umbiegen."""
    for d in iter_dicts(node):
        if d.get("type") == ActionType.WORKSPACE and d.get("id") in ids:
            d["id"] = ids[d["id"]]


def _unique(name: str, taken: set[str]) -> str:
    out, n = name, 2
    while out.casefold() in taken:
        out, n = f"{name} {n}", n + 1
    return out


def insert_into(profile: Profile, template_ids: Iterable[str]) -> list[Inserted]:
    """Arbeitsbereiche der Vorlagen hinten an ``profile`` anhaengen (neue Kennungen, Namen
    eindeutig) und je Arbeitsbereich die erste freie runde Taste darauf legen. Die runden und
    eckigen Tasten der Vorlage selbst gelten fuers ganze Profil und bleiben deshalb draussen.
    Prueft erst alle Vorlagen, dann aendert es ``profile`` (``ValueError``: nichts geaendert)."""
    loaded = [_valid(t) for t in template_ids]
    ws_ids = {w.id for w in profile.workspaces}
    names = {w.name.casefold() for w in profile.workspaces}
    out: list[Inserted] = []
    for data in loaded:
        ids = {}
        for ws in data.get("workspaces", []):
            new = new_uuid_id("ws-", ws_ids, 8)
            ws_ids.add(new)
            ids[ws["id"]] = new
        _retarget(data["workspaces"], ids)
        for ws in data["workspaces"]:
            ws["id"] = ids[ws["id"]]
        for ws in Profile.from_json(data).workspaces:
            ws.name = _unique(ws.name or tr("Vorlage"), names)
            names.add(ws.name.casefold())
            profile.workspaces.append(ws)
            code = next((c for c in ROUND_CODES if profile.round.get(c) is None), None)
            if code is not None:
                profile.round[code] = Assignment({"type": ActionType.WORKSPACE, "id": ws.id})
            out.append(Inserted(ws.id, ws.name, code))
    if not profile.home_workspace and profile.workspaces:
        profile.home_workspace = profile.workspaces[0].id
    return out


def insert_pages(workspace: Workspace, template_ids: Iterable[str]) -> list[str]:
    """Nur die Seiten der Vorlagen hinten an ``workspace`` haengen (ohne Regler, Rad und
    runde Tasten). Seiten-IDs werden neu vergeben; Ordner-Tasten und Aktionen ``page`` (Seite
    per Nummer) zeigen weiter auf ihre Seite. Liefert die Namen der neuen Seiten; prueft erst
    alle Vorlagen (``ValueError``: nichts geaendert)."""
    loaded = [_valid(t) for t in template_ids]
    ids = {p.id for p in workspace.touch_pages}
    names: list[str] = []
    for data in loaded:
        for ws in data.get("workspaces", []):
            pages = ws.get("touch_pages", [])
            offset = len(workspace.touch_pages)
            new_ids = {}
            for page in pages:
                new_ids[page["id"]] = new_page_id(ids, len(ids) + 1)
                ids.add(new_ids[page["id"]])
            for node in iter_dicts(pages):
                if node.get("type") == ActionType.FOLDER and node.get("page") in new_ids:
                    node["page"] = new_ids[node["page"]]
                elif node.get("type") == ActionType.PAGE and isinstance(node.get("index"), int):
                    node["index"] += offset
            for page in pages:
                page["id"] = new_ids[page["id"]]
                if page.get("parent") in new_ids:
                    page["parent"] = new_ids[page["parent"]]
                workspace.touch_pages.append(TouchPage.from_json(page))
                names.append(page.get("name") or page["id"])
    return names


def instantiate(template_id: str, existing: Iterable[str],
                name: str | None = None) -> Profile:
    """Neues Profil aus der Vorlage (Kennung ``<vorlage>-<zufall>``, noch nicht gespeichert)."""
    data = _valid(template_id)
    data["id"] = new_uuid_id(f"{template_id}-", set(existing), 6)
    if name:
        data["name"] = name
    return Profile.from_json(data)
