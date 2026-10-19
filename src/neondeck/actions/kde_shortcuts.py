"""Aktion „KDE-Kürzel auslösen“ und die Liste aller globalen Kürzel (kglobalaccel).

Ausgeloest wird ueber ``org.kde.kglobalaccel /component/<komponente>
org.kde.kglobalaccel.Component.invokeShortcut <name>`` – ohne Tastendruck, also auch fuer
Kuerzel ohne Tastenbelegung. Den Objektpfad bildet kglobalaccel aus dem eindeutigen Namen
der Komponente: jedes Zeichen ausser Buchstaben, Ziffern und ``_`` wird zu ``_``
(``org.kde.spectacle.desktop`` -> ``/component/org_kde_spectacle_desktop``).

``list_shortcuts`` fragt ``allComponents`` und je Komponente ``allShortcutInfos`` ab
(``qdbus --literal``, belegt 18.10.2026 an Plasma 6.7: je Kuerzel ``(ssssssaiai)`` =
Name, Anzeigename, Komponente, Anzeigename der Komponente, Kontext, Kontextname, Tasten,
Standardtasten). Blockiert mehrere Prozessaufrufe lang: nie im GUI-Thread (API
``kde.shortcuts`` liest im Hintergrund und merkt sich das Ergebnis).
"""
from __future__ import annotations

import re
from collections.abc import Callable

from ..core import proc
from ..core.i18n import N_, tr
from .base import ActionContext, Param, Result, qdbus, register

SERVICE = "org.kde.kglobalaccel"
COMPONENT_IFACE = "org.kde.kglobalaccel.Component"
_PATH_CHARS = re.compile(r"[^A-Za-z0-9_]")
_OBJECT_PATH = re.compile(r"ObjectPath: (/component/[A-Za-z0-9_]+)\]")
_STR = r'"((?:[^"\\]|\\.)*)"'
_INFO = re.compile(r"\(ssssssaiai\) " + ", ".join([_STR] * 3))
_UNESCAPE = re.compile(r"\\(.)")


def component_path(component: str) -> str:
    return "/component/" + _PATH_CHARS.sub("_", component)


def _text(literal: str) -> str:
    return _UNESCAPE.sub(r"\1", literal)


def list_shortcuts(run: Callable | None = None) -> list[tuple[str, str, str]]:
    """Alle globalen Kuerzel als ``(komponente, name, anzeigename)``; leer, wenn
    kglobalaccel oder ``qdbus`` fehlt."""
    run = run or proc.run

    def literal(path: str, method: str) -> str:
        try:
            p = run(proc.qdbus_argv(SERVICE, path, method, literal=True))
        except (OSError, proc.SubprocessError):
            return ""
        return (p.stdout or "") if p.returncode == 0 else ""

    out: list[tuple[str, str, str]] = []
    for path in _OBJECT_PATH.findall(literal("/kglobalaccel",
                                             "org.kde.KGlobalAccel.allComponents")):
        for raw_name, friendly, component in _INFO.findall(
                literal(path, f"{COMPONENT_IFACE}.allShortcutInfos")):
            name = _text(raw_name)
            out.append((_text(component), name, _text(friendly) or name))
    return out


def invoke(ctx: ActionContext, component: str, name: str) -> Result:
    """Kuerzel ``name`` der Komponente ``component`` ausloesen (ohne Tastendruck)."""
    return qdbus(ctx, SERVICE, component_path(component), f"{COMPONENT_IFACE}.invokeShortcut",
                 name)


@register("kde_shortcut", label=N_("KDE-Kürzel auslösen"), category="system", params=[
    Param("component", N_("Komponente"), "text", "kwin"), Param("name", N_("Kürzel"), "text")])
def kde_shortcut(action, ctx, **_):
    component = str(action.get("component") or "").strip()
    name = str(action.get("name") or "")
    if not component or not name:
        return Result(False, tr("Kein KDE-Kürzel angegeben"))
    res = invoke(ctx, component, name)
    return Result(res.ok, "" if res.ok else res.message)
