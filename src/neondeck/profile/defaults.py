"""Das mitgelieferte Standardprofil (aus dem Windows-Standardprofil umgewandelt)."""
from __future__ import annotations

import logging
from pathlib import Path

from ..core.fileio import read_json
from ..core.i18n import tr
from .importers.windows import convert
from .model import Profile, empty_profile
from .store import DEFAULT_ID, DEFAULT_NAME, ProfileStore

log = logging.getLogger(__name__)


def ensure_default(store: ProfileStore, assets_dir: Path) -> Profile:
    """Legt ``default.json`` aus dem Windows-Standardprofil an, falls es fehlt; sonst laden."""
    if store.path(DEFAULT_ID).exists():
        return store.load(DEFAULT_ID)
    return regenerate_default(store, assets_dir)


def regenerate_default(store: ProfileStore, assets_dir: Path) -> Profile:
    """Erzeugt ``default.json`` neu aus dem Windows-Standardprofil und speichert es.

    Ohne lesbare Vorlage: leeres Profil, ``default.json`` bleibt unveraendert.
    """
    src = Path(assets_dir) / "defaults" / "DefaultProfile20"
    try:
        info = read_json(src / "ProfileInfo.json")
    except (OSError, ValueError) as e:
        log.error("Windows-Standardprofil nicht lesbar (%s); leeres Profil", e)
        return empty_profile(DEFAULT_ID)
    profile, messages = convert(info, src / "ActionIcons", icon_out_dir=src / "linux-icons")
    for m in messages:
        log.warning("Standardprofil: %s", m)
    profile.id, profile.name = DEFAULT_ID, tr(DEFAULT_NAME)
    store.save(profile)
    return profile
