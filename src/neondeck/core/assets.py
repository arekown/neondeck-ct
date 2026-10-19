"""Original-Grafiken: Import in das Datenverzeichnis, Aufloesung von Referenzen, Katalog."""
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .i18n import N_

_GENERIC = "app/service/ProgramFiles64Folder/Logi/LogiPluginService/Plugins/@Generic"
_UNPACKED = "assets-unpacked"
ROOT_GROUP = N_("Allgemein")
CATALOG_SIZE = "80x80"


@dataclass(frozen=True)
class IconEntry:
    ref: str
    group: str
    name: str


def assets_dir() -> Path:
    return paths.data_dir() / "assets"


def _copy(src: Path, dst: Path) -> None:
    """Kopiert nur, wenn das Ziel fehlt oder Groesse/mtime abweichen."""
    if dst.exists():
        s, d = src.stat(), dst.stat()
        if s.st_size == d.st_size and s.st_mtime_ns == d.st_mtime_ns:
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, pattern: str = "*", flat: bool = False) -> int:
    n = 0
    if not src.is_dir():
        return 0
    for f in sorted(src.rglob(pattern)):
        if not f.is_file():
            continue
        rel = Path(f.name) if flat else f.relative_to(src)
        _copy(f, dst / rel)
        n += 1
    return n


def import_assets(source: Path) -> dict[str, int]:
    source = Path(source)
    un = source / _UNPACKED
    gen = source / _GENERIC
    out = assets_dir()
    manifest = {
        "library": _copy_tree(un / "imagelib-Loupedeck_de-DE", out / "library" / "de"),
        "library_neutral": _copy_tree(un / "imagelib-Loupedeck", out / "library" / "neutral"),
        "actionicons": _copy_tree(gen / "actionicons", out / "actionicons", "*.svg"),
        "actionsymbols": _copy_tree(gen / "actionsymbols", out / "actionsymbols", "*.svg"),
        "icons": _copy_tree(un / "licons-DefaultIcons", out / "icons", "*.svg", flat=True),
        "sounds": _copy_tree(un / "lsounds-LoupedeckSoundPack", out / "sounds", "*.wav", flat=True),
        "defaults": _copy_tree(un / "lp5-DefaultProfile20", out / "defaults" / "DefaultProfile20"),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def resolve(ref: str) -> Path | None:
    """Loest eine Bildreferenz (lib:/svg:/file:) in einen vorhandenen Dateipfad auf."""
    kind, sep, rest = ref.partition(":")
    if not sep or not rest:
        return None
    if kind == "file":
        p = Path(rest)
        return p if p.is_file() else None
    root = assets_dir()
    rp = Path(rest)
    if rp.is_absolute() or ".." in rp.parts:
        return None
    if kind == "lib":
        for lang in ("de", "neutral"):
            p = root / "library" / lang / rest
            if p.is_file():
                return p
        return None
    if kind == "svg":
        if rp.parts[0] not in ("actionicons", "actionsymbols", "icons"):
            return None
        p = root / rest
        return p if p.is_file() else None
    return None


def catalog() -> list[IconEntry]:
    root = assets_dir()
    entries: dict[str, IconEntry] = {}
    for lang in ("de", "neutral"):
        base = root / "library" / lang / CATALOG_SIZE
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.png")):
            rel = f.relative_to(base)
            ref = f"lib:{CATALOG_SIZE}/{rel.as_posix()}"
            if ref not in entries:
                group = rel.parts[0] if len(rel.parts) > 1 else ROOT_GROUP
                entries[ref] = IconEntry(ref, group, f.stem)
    result = list(entries.values())
    for folder, group in (("actionicons", N_("Aktions-Icons")), ("actionsymbols", N_("Symbole")),
                          ("icons", N_("Icons"))):
        d = root / folder
        if d.is_dir():
            result.extend(IconEntry(f"svg:{folder}/{f.name}", group, f.stem)
                          for f in sorted(d.glob("*.svg")))
    return result
