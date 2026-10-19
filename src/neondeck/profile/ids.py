"""IDs fuer Profile, Arbeitsbereiche und Seiten sowie die Ablage importierter Symbole (Qt-frei)."""
from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Callable, Container
from pathlib import Path

from ..core import paths
from .model import Profile

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slugify(name: str) -> str:
    """``"Größe & Übung"`` -> ``"groesse-uebung"``; leer -> ``"profil"``."""
    s = unicodedata.normalize("NFKD", name.casefold().translate(_UMLAUTS))
    s = re.sub(r"[^a-z0-9]+", "-", s.encode("ascii", "ignore").decode()).strip("-")
    return s[:40].strip("-") or "profil"


def new_uuid_id(prefix: str, existing: Container[str], n_hex: int,
                taken: Callable[[str], bool] | None = None) -> str:
    """``<prefix><zufall>`` (``n_hex`` Hex-Ziffern), nicht in ``existing`` und, falls
    angegeben, nicht ``taken(id)``."""
    while True:
        candidate = f"{prefix}{uuid.uuid4().hex[:n_hex]}"
        if candidate not in existing and not (taken is not None and taken(candidate)):
            return candidate


def new_profile_id(name: str, existing) -> str:
    return new_uuid_id(f"{slugify(name)}-", existing, 6)


def new_page_id(existing: Container[str], start: int) -> str:
    """Erste freie Seiten-ID ``p<n>`` ab ``n = start``."""
    n = start
    while f"p{n}" in existing:
        n += 1
    return f"p{n}"


def new_workspace_id(profile: Profile) -> str:
    ids = {w.id for w in profile.workspaces}
    n = len(ids) + 1
    while f"ws{n}" in ids:
        n += 1
    return f"ws{n}"


def imported_root() -> Path:
    return paths.data_dir() / "imported"


def imported_dir(pid: str) -> Path:
    """Ablage der Symbole und Bilder eines importierten Profils (.lp5 und .ndprofile)."""
    return imported_root() / pid
