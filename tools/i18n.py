#!/usr/bin/env python3
"""Sprachdateien ``data/i18n/<code>.json`` mit den Texten im Programm abgleichen.

Aufruf: ``python3 tools/i18n.py --check`` meldet je Sprache fehlende Texte (auch leere
Werte), Texte mit anderen Platzhaltern und veraltete Eintraege (Exit-Code 1, wenn etwas
fehlt oder Platzhalter abweichen). ``python3 tools/i18n.py --update`` traegt fehlende Texte
als ``"Text": ""`` ein (leer = deutscher Rueckfall) und meldet veraltete nur – geloescht
wird nichts.

Gesammelt werden alle Literale in ``tr("…")``/``N_("…")`` unter ``src/`` (per ``ast``, auch
``i18n.tr(…)``) und die Anzeigetexte der Vorlagen ``data/templates/*.json``
(``profile.templates.template_texts``).
"""
from __future__ import annotations

import argparse
import ast
import json
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neondeck.core.fileio import read_json, write_atomic  # noqa: E402 - nach sys.path
from neondeck.core.i18n import META  # noqa: E402 - nach sys.path
from neondeck.profile.templates import template_texts  # noqa: E402 - nach sys.path

MARKERS = ("tr", "N_")


def _marker(func: ast.expr) -> bool:
    """``tr(…)``, ``N_(…)`` oder ``i18n.tr(…)`` (nicht ``self.tr`` von Qt)."""
    if isinstance(func, ast.Name):
        return func.id in MARKERS
    return (isinstance(func, ast.Attribute) and func.attr in MARKERS
            and isinstance(func.value, ast.Name) and func.value.id == "i18n")


def extract_source(src: Path) -> dict[str, list[str]]:
    """Text -> Fundstellen (``pfad:zeile``) aller markierten Literale unter ``src``."""
    out: dict[str, list[str]] = {}
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _marker(node.func) and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
                    where = f"{path.relative_to(ROOT)}:{node.lineno}"
                    out.setdefault(arg.value, []).append(where)
    return out


def extract_templates(folder: Path) -> dict[str, list[str]]:
    """Text -> Vorlagen (``data/templates/<id>.json``), in denen er vorkommt."""
    out: dict[str, list[str]] = {}
    for path in sorted(folder.glob("*.json")):
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        for node, key in template_texts(data):
            where = str(path.relative_to(ROOT))
            places = out.setdefault(node[key], [])
            if where not in places:
                places.append(where)
    return out


def extract(root: Path = ROOT) -> dict[str, list[str]]:
    """Alle zu uebersetzenden Texte mit Fundstellen (Quelltext zuerst, dann Vorlagen)."""
    out = extract_source(root / "src")
    for text, places in extract_templates(root / "data" / "templates").items():
        out.setdefault(text, []).extend(places)
    return out


def placeholders(text: str) -> set[str]:
    """Platzhalter eines Texts (``{name}``, ``{id!r}`` …); kaputte Klammern: leer."""
    try:
        return {f"{name}!{conv}" if conv else name
                for _, name, _, conv in string.Formatter().parse(text) if name is not None}
    except ValueError:
        return set()


def compare(texts: dict, catalog: dict) -> tuple[list[str], list[str], list[str]]:
    """``(fehlend, andere_platzhalter, veraltet)`` einer Sprachdatei gegen ``texts``."""
    missing = [t for t in texts if not catalog.get(t)]
    mismatched = [t for t in texts if catalog.get(t) and isinstance(catalog[t], str)
                  and placeholders(catalog[t]) != placeholders(t)]
    stale = [k for k in catalog if k != META and k not in texts]
    return missing, mismatched, stale


def language_files(root: Path = ROOT) -> list[Path]:
    return sorted((root / "data" / "i18n").glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sprachdateien mit dem Programm abgleichen")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="nur melden (Standard)")
    mode.add_argument("--update", action="store_true",
                      help="fehlende Texte mit leerem Wert eintragen")
    args = ap.parse_args(argv)
    texts = extract()
    bad = False
    for path in language_files():
        catalog = read_json(path)
        missing, mismatched, stale = compare(texts, catalog)
        print(f"{path.name}: {len(texts)} Texte, {len(missing)} fehlend, "
              f"{len(mismatched)} mit anderen Platzhaltern, {len(stale)} veraltet")
        for text in mismatched:
            print(f"  Platzhalter: {text!r} -> {catalog[text]!r}")
        for text in stale:
            print(f"  veraltet: {text!r}")
        if args.update:
            new = [t for t in missing if t not in catalog]
            if new:
                catalog.update(dict.fromkeys(new, ""))
                write_atomic(path, json.dumps(catalog, ensure_ascii=False, indent=1) + "\n")
                print(f"  {len(new)} neue Texte eingetragen")
        else:
            for text in missing:
                print(f"  fehlt: {text!r} ({texts[text][0]})")
        bad = bad or bool(mismatched) or (not args.update and bool(missing))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
