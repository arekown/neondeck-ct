"""Einzelne Profile austauschen: ``.ndprofile`` (Zip mit ``profile.json`` und ``files/``);
das fruehere ``.ldlprofile`` (gleicher Aufbau) wird weiter gelesen.

Export: eigene Bilder (``file:``-Verweise, die es gibt) kommen nach ``files/`` und werden im
Archiv als ``file:files/<name>`` verwiesen. Import: Eintraege werden wie beim .lp5-Import
geprueft (``safe_extract``), das Profil vorher wie ueber die API geprueft
(``validate_profile_json``), die Bilder landen in ``data_dir()/imported/<id>/`` und die
Verweise zeigen dorthin. Das Profil bekommt eine Kennung, die es noch nicht gibt (ein Import
ersetzt nie ein vorhandenes Profil); gespeichert wird beim Aufrufer (Editor: ueber den Dienst).
"""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

from ..core.fileio import read_json, write_atomic
from ..core.i18n import tr
from ..core.values import join_errors
from .archive import safe_extract
from .ids import imported_dir, new_uuid_id
from .model import Profile, validate_profile_json
from .walk import rewrite_values

EXTENSION = ".ndprofile"
LEGACY_EXTENSION = ".ldlprofile"  # Export vor der Umbenennung; Import liest beide
IMPORT_EXTENSIONS = (EXTENSION, LEGACY_EXTENSION)
PROFILE_FILE = "profile.json"
FILES_DIR = "files"
FORMAT = "ndprofile"
FORMATS = (FORMAT, "ldlprofile")  # Kennung im Archiv; die fruehere wird weiter gelesen
_FILE = "file:"
_ARCHIVED = f"{_FILE}{FILES_DIR}/"


def _rewrite_refs(node, fn: Callable[[str], str]) -> None:
    """Jeden Bildverweis (Schluessel ``icon``) im Profil-JSON durch ``fn(verweis)`` ersetzen."""
    rewrite_values(node, "icon", fn)


def export_profile(profile: Profile, dest: Path) -> list[str]:
    """Profil nach ``dest`` schreiben (atomar); liefert fehlende Bilder (bleiben verwiesen)."""
    data = profile.to_json()
    files: dict[str, Path] = {}   # Archivname -> Quelle
    names: dict[str, str] = {}    # Quelle -> Archivname
    missing: list[str] = []

    def archive_ref(ref: str) -> str:
        if not ref.startswith(_FILE):
            return ref
        src = Path(ref[len(_FILE):])
        if not src.is_absolute() or not src.is_file():
            missing.append(ref[len(_FILE):])
            return ref
        key = str(src.resolve())
        if key not in names:
            name = src.name
            n = 1
            while name in files:
                n += 1
                name = f"{src.stem}-{n}{src.suffix}"
            names[key], files[name] = name, src
        return _ARCHIVED + names[key]

    _rewrite_refs(data, archive_ref)
    dest = Path(dest)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(PROFILE_FILE, json.dumps({"format": FORMAT, "profile": data},
                                            ensure_ascii=False, indent=2))
        for name, src in files.items():
            z.write(src, f"{FILES_DIR}/{name}")
    write_atomic(dest, buf.getvalue())
    return missing


def import_profile(archive: Path, existing: Iterable[str]) -> Profile:
    """``.ndprofile`` (oder ``.ldlprofile``) lesen; Bilder nach ``imported/<neue id>/``
    kopieren, Profil zurueck (noch nicht gespeichert). Jeder Fehler -> ``ValueError``/
    ``OSError`` (deutsch), dann bleibt nichts liegen."""
    existing = set(existing)
    with tempfile.TemporaryDirectory(prefix="neondeck-share-") as tmp:
        root = Path(tmp)
        safe_extract(Path(archive), root, what=tr("{ext}-Datei", ext=EXTENSION))
        try:
            outer = read_json(root / PROFILE_FILE)
        except FileNotFoundError:
            raise ValueError(tr("{file} fehlt im Archiv", file=PROFILE_FILE)) from None
        except (OSError, ValueError) as e:
            raise ValueError(tr("{file} unlesbar ({e})", file=PROFILE_FILE, e=e)) from e
        data = outer.get("profile") if isinstance(outer, dict) and \
            outer.get("format") in FORMATS else outer
        errors = validate_profile_json(data)
        if errors:
            raise ValueError(tr("Profil ungültig: {errors}", errors=join_errors(errors, 5)))
        pid = data["id"]
        if pid in existing or imported_dir(pid).exists():
            pid = _new_id(pid, existing)
        data["id"] = pid
        src_files = root / FILES_DIR
        out = imported_dir(pid)

        def local_ref(ref: str) -> str:
            if not ref.startswith(_ARCHIVED):
                return ref
            name = ref[len(_ARCHIVED):]
            src = src_files / name
            if "/" in name or not src.is_file():
                return ref  # fehlt im Archiv: Verweis bleibt (Taste zeigt dann Text)
            return f"{_FILE}{out / name}"

        _rewrite_refs(data, local_ref)
        done = False
        try:
            if src_files.is_dir() and any(src_files.iterdir()):
                shutil.copytree(src_files, out, dirs_exist_ok=True)
            profile = Profile.from_json(data)
            done = True
            return profile
        finally:
            if not done:
                shutil.rmtree(out, ignore_errors=True)


def _new_id(pid: str, existing: set[str]) -> str:
    return new_uuid_id(f"{pid[:80]}-", existing, 6, taken=lambda c: imported_dir(c).exists())
