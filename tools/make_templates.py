#!/usr/bin/env python3
"""Erzeugt die mitgelieferten Vorlagen ``data/templates/<id>.json`` aus ``tools/templates/``.

Aufruf: ``python3 tools/make_templates.py`` (ueberschreibt nur die dort definierten Vorlagen;
handgeschriebene wie ``medien.json`` bleiben unberuehrt). Jede Vorlage wird vor dem Schreiben
mit ``validate_profile_json`` geprueft.

Die Definitionen stehen nach Kategorie in ``tools/templates/*.py`` (Daten), die Bausteine
(Tastenkuerzel, Tasten, Regler, ``template``) in ``tools/templates/build.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from templates import TEMPLATES  # noqa: E402 - erst nach sys.path

from neondeck.profile.model import validate_profile_json  # noqa: E402 - nach sys.path

OUT = ROOT / "data" / "templates"


def check(templates: list[dict]) -> None:
    """Doppelte Kennungen/LED-Farben und ungueltiges Format -> ``ValueError``."""
    ids = [t["id"] for t in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("doppelte Vorlagen-ID")
    leds = [t["workspaces"][0]["led_color"] for t in templates]
    if len(leds) != len(set(leds)):
        raise ValueError("doppelte LED-Farbe")
    for t in templates:
        errors = validate_profile_json(t)
        if errors:
            raise ValueError(f"Vorlage {t['id']} ungueltig: {'; '.join(errors)}")


def main() -> None:
    check(TEMPLATES)
    for t in TEMPLATES:
        (OUT / f"{t['id']}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")
    print(f"{len(TEMPLATES)} Vorlagen geschrieben nach {OUT}")


if __name__ == "__main__":
    main()
