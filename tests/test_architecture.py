"""Schichtenregel: ``core ← device ← profile ← render ← actions ← engine ← desktop ← api``,
darüber ``ui`` und ``service``/``editor``; nur nach unten importieren, kein Qt unterhalb von
``desktop``, keine Kreise. Ein Test über den Importgraphen (``ast``, kein Import der Module)."""
from __future__ import annotations

import ast
from pathlib import Path

PKG = "neondeck"
SRC = Path(__file__).resolve().parents[1] / "src" / PKG

RANK = {"core": 0, "device": 1, "profile": 2, "render": 3, "actions": 4, "engine": 5,
        "desktop": 6, "api": 7, "ui": 8, "service": 9, "editor": 9}
FREI = {"cli", "diagnose", "__main__"}  # dürfen alles
QT_FREI = {"core", "device", "profile", "actions", "engine"}

# Heutige Verstöße (Importer, Ziel): Die Liste darf nur kürzer werden, nie länger.
SCHICHT_AUSNAHMEN: set[tuple[str, str]] = set()
QT_AUSNAHMEN: set[tuple[str, str]] = set()


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _graph() -> tuple[dict[str, set[str]], set[tuple[str, str]]]:
    """Modul -> importierte Projektmodule; dazu (Modul, Qt-Paket)-Paare."""
    files = {_module_name(p): p for p in SRC.rglob("*.py")}
    edges: dict[str, set[str]] = {m: set() for m in files}
    qt: set[tuple[str, str]] = set()
    for mod, path in files.items():
        is_pkg = path.name == "__init__.py"
        pkg = mod.split(".") if is_pkg else mod.split(".")[:-1]
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                qt |= {(mod, a.name) for a in node.names if a.name.split(".")[0] == "PySide6"}
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = pkg[:len(pkg) - node.level + 1] + (node.module or "").split(".")
                    base = [b for b in base if b]
                elif (node.module or "").split(".")[0] == "PySide6":
                    qt.add((mod, node.module))
                    continue
                elif (node.module or "").split(".")[0] == PKG:
                    base = node.module.split(".")[1:]
                else:
                    continue
                for a in node.names:
                    sub = ".".join([*base, a.name])
                    target = sub if sub in files else ".".join(base)
                    if target in files and target != mod:
                        edges[mod].add(target)
    return edges, qt


def _layer(mod: str) -> str:
    return mod.split(".")[0]


def _cycles(edges: dict[str, set[str]]) -> list[str]:
    """Module, die über ihre Importe wieder sich selbst erreichen."""
    def reaches_itself(start: str) -> bool:
        todo, seen = list(edges[start]), set()
        while todo:
            m = todo.pop()
            if m == start:
                return True
            if m not in seen:
                seen.add(m)
                todo.extend(edges[m])
        return False

    return sorted(m for m in edges if reaches_itself(m))


def test_architecture():
    edges, qt = _graph()
    schicht = set()
    for mod, targets in edges.items():
        a = _layer(mod)
        if a in FREI or a not in RANK:
            continue
        for t in targets:
            b = _layer(t)
            if b != a and b in RANK and RANK[b] >= RANK[a]:
                schicht.add((mod, t))
    qt_verstoss = {(m, q) for m, q in qt if _layer(m) in QT_FREI}
    assert schicht == SCHICHT_AUSNAHMEN
    assert qt_verstoss == QT_AUSNAHMEN
    assert _cycles(edges) == []


def test_contracts_are_fulfilled():
    """Die Protokolle aus ``api.contracts`` passen zu ihren Umsetzungen (ohne Typprüfer)."""
    from neondeck.api import contracts
    from neondeck.editor.remote.engine import RemoteEngine
    from neondeck.editor.remote.store import RemoteStore
    from neondeck.engine import Engine
    from neondeck.profile.store import ProfileStore
    from neondeck.service.app import App

    def members(proto) -> set[str]:
        names = {n for n in vars(proto) if not n.startswith("_")}
        return names | set(getattr(proto, "__annotations__", {}))

    instance_attrs = {"profile", "workspace_id", "page_index", "engine", "store", "settings",
                      "settings_controller", "api"}  # erst im __init__ gesetzt
    for proto, impls in ((contracts.EditorBackend, (Engine, RemoteEngine)),
                         (contracts.ServiceLink, (RemoteEngine,)),
                         (contracts.ProfileRepository, (ProfileStore, RemoteStore)),
                         (contracts.ServiceFacade, (App,))):
        for impl in impls:
            missing = {n for n in members(proto) - instance_attrs if not hasattr(impl, n)}
            assert not missing, f"{impl.__name__} fehlt {sorted(missing)} aus {proto.__name__}"
