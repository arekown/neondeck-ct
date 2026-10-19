"""Windows-Profile (.lp5) importieren und nicht mehr benutzte Import-Ordner aufraeumen.

Qt-frei: der Editor ruft ``import_lp5`` aus dem Profil-Dialog, der Dienst
``remove_unused_imports`` nach ``profile.delete``.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from ...core.fileio import read_json
from ...core.i18n import tr
from ..archive import safe_extract
from ..ids import imported_dir, imported_root, new_profile_id
from ..model import Profile
from ..store import ProfileStore
from .windows import convert

log = logging.getLogger(__name__)


def _find_profile_info(root: Path) -> Path:
    found = [p for p in root.rglob("*") if p.is_file() and p.name.casefold() == "profileinfo.json"]
    if not found:
        raise ValueError(tr("ProfileInfo.json fehlt im Archiv"))
    return min(found, key=lambda p: (len(p.parts), str(p)))


def remove_unused_imports(store: ProfileStore) -> None:
    """Ordner ``imported/<id>`` entfernen, die kein Profil mehr nutzt (geloeschtes Profil,
    liegengebliebene Reste); eine Kopie, die die Symbole nutzt, haelt sie (Dienst, nach
    ``profile.delete``)."""
    root = imported_root()
    if not root.is_dir():
        return
    ids = set(store.list())
    texts = []
    for pid in ids:
        try:
            texts.append(store.path(pid).read_text(encoding="utf-8"))
        except OSError:
            return  # unklar, wer was nutzt: nichts loeschen
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name in ids:
            continue
        needles = {f"{folder}/", f"{folder.resolve()}/"}
        if not any(n in t for n in needles for t in texts):
            shutil.rmtree(folder, ignore_errors=True)


def import_lp5(archive: Path, store: ProfileStore) -> tuple[Profile, list[str]]:
    """Windows-Profil als neues Profil speichern; liefert es und die Liste der Hinweise
    (nicht umsetzbare Aktionen). Jeder Fehler -> ``ValueError``/``OSError`` mit deutscher
    Meldung, nichts gespeichert."""
    try:
        return _import_lp5(Path(archive), store)
    except (ValueError, OSError):
        raise
    except Exception as e:
        log.exception("Import von %s fehlgeschlagen", archive)
        raise ValueError(tr("Windows-Profil nicht lesbar ({kind}: {e})", kind=type(e).__name__, e=e)) from e


def _import_lp5(archive: Path, store: ProfileStore) -> tuple[Profile, list[str]]:
    with tempfile.TemporaryDirectory(prefix="neondeck-lp5-") as tmp:
        safe_extract(archive, Path(tmp))
        info_path = _find_profile_info(Path(tmp))
        try:
            info = read_json(info_path)
        except (OSError, ValueError) as e:
            raise ValueError(tr("ProfileInfo.json unlesbar ({e})", e=e)) from e
        if not isinstance(info, dict):
            raise ValueError(tr("ProfileInfo.json ist kein Profil"))
        name = str(info.get("displayName") or archive.stem)
        pid = new_profile_id(name, set(store.list()))
        base, out = info_path.parent, imported_dir(pid)
        ict = base / "ActionIcons"
        images = base / "ActionImages"
        done = False
        try:
            if images.is_dir():  # die Bilder bleiben am Ort liegen, auf den das Profil zeigt
                shutil.copytree(images, out / "ActionImages")
            try:
                profile, messages = convert(info, ict if ict.is_dir() else None,
                                            icon_out_dir=out, images_dir=out / "ActionImages")
            except Exception as e:
                log.exception("Umwandeln von %s fehlgeschlagen", archive)
                raise ValueError(tr("Das Windows-Profil hat ein unerwartetes Format ({e})", e=e)) from e
            profile.id, profile.name = pid, name
            store.save(profile)
            done = True
        finally:
            if not done:
                shutil.rmtree(out, ignore_errors=True)
    log.info("Windows-Profil %s als %s importiert (%d Hinweise)", archive, pid, len(messages))
    return profile, messages
