"""Schriften fuer die Displaybilder: Noto Sans (System) und die mitgelieferten aus
``data/fonts`` (Inter, Orbitron, Rajdhani, Share Tech Mono).

Gezeichnet wird im Dienst-Prozess mit Pillow: die Dateien werden ueber ihren Pfad geladen
(nicht ueber die Qt-Schriftdatenbank). Fehlt eine Datei, gilt Noto Sans, fehlt auch die,
Pillows eingebaute Schrift.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from ..core.paths import fonts_dir

log = logging.getLogger(__name__)

# Noto Sans der Distribution: Fedora, Debian/Ubuntu, Arch
NOTO_DIRS = ("/usr/share/fonts/google-noto/", "/usr/share/fonts/truetype/noto/",
             "/usr/share/fonts/noto/")
DEFAULT_FAMILY = "Noto Sans"


def _noto(name: str) -> Path:
    """Datei im ersten Noto-Ordner, der sie hat (sonst der erste: die Diagnose meldet sie)."""
    return next((p for d in NOTO_DIRS if (p := Path(d) / name).is_file()),
                Path(NOTO_DIRS[0]) / name)


def _bundled(rel: str) -> Path:
    return fonts_dir() / rel


# Familie -> (Datei normal, Datei fett, Variante fett bei variablen Schriften)
_FILES: dict[str, tuple] = {
    "Noto Sans": (lambda: _noto("NotoSans-Regular.ttf"), lambda: _noto("NotoSans-Bold.ttf"),
                  None),
    "Inter": (lambda: _bundled("inter/Inter-VariableFont_opsz,wght.ttf"),
              lambda: _bundled("inter/Inter-VariableFont_opsz,wght.ttf"), b"Bold"),
    "Orbitron": (lambda: _bundled("orbitron/Orbitron-VariableFont_wght.ttf"),
                 lambda: _bundled("orbitron/Orbitron-VariableFont_wght.ttf"), b"Bold"),
    "Rajdhani": (lambda: _bundled("rajdhani/Rajdhani-Medium.ttf"),
                 lambda: _bundled("rajdhani/Rajdhani-Bold.ttf"), None),
    "Share Tech Mono": (lambda: _bundled("sharetechmono/ShareTechMono-Regular.ttf"),
                        lambda: _bundled("sharetechmono/ShareTechMono-Regular.ttf"), None),
}
FAMILIES: tuple[str, ...] = tuple(_FILES)


def font_files() -> dict[str, Path]:
    """Familie -> Datei der normalen Schnittart (Diagnose: sind alle da?)."""
    return {family: files[0]() for family, files in _FILES.items()}


def _load(family: str, size: int, bold: bool) -> ImageFont.FreeTypeFont | None:
    regular, heavy, variation = _FILES[family]
    path = (heavy if bold else regular)()
    try:
        fnt = ImageFont.truetype(str(path), size)
    except OSError:
        return None
    if bold and variation is not None:
        try:
            fnt.set_variation_by_name(variation)
        except (OSError, ValueError) as e:  # Schrift ohne die Variante: normal laden
            log.debug("Schrift %s: Variante %s nicht setzbar: %s", family, variation, e)
    return fnt


@lru_cache(maxsize=256)
def font(size: int, bold: bool = False, family: str | None = None) -> ImageFont.FreeTypeFont:
    """Schrift ``family`` (unbekannt oder ``None``: Noto Sans) in ``size`` Pixeln."""
    family = family if family in _FILES else DEFAULT_FAMILY
    fnt = _load(family, size, bold)
    if fnt is None and family != DEFAULT_FAMILY:
        log.warning("Schrift %s nicht ladbar – %s", family, DEFAULT_FAMILY)
        fnt = _load(DEFAULT_FAMILY, size, bold)
    return fnt if fnt is not None else ImageFont.load_default(size)
