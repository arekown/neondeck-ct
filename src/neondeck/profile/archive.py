"""Zip-Archive sicher entpacken (Windows-Profile ``.lp5``, Profil-Austausch ``.ndprofile``)."""
from __future__ import annotations

import re
import shutil
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from ..core.i18n import tr

MAX_UNPACKED = 512 * 1024 * 1024    # Archiv entpackt hoechstens so gross
# Was ein kaputtes oder fremdes Archiv beim Lesen ausloest (neben OSError)
ARCHIVE_ERRORS = (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, EOFError)


def member_parts(name: str) -> tuple[str, ...]:
    """Pfadteile eines Archiveintrags; absolut oder mit ``..`` -> ``ValueError``."""
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        raise ValueError(tr("Unsicherer Pfad im Archiv: {name}", name=name))
    parts = PurePosixPath(n).parts
    if ".." in parts:
        raise ValueError(tr("Unsicherer Pfad im Archiv: {name}", name=name))
    return parts


def safe_extract(archive: Path, dest: Path, what: str | None = None) -> None:
    """Entpackt ``archive`` nach ``dest``; prueft vorher jeden Eintrag (nichts halb entpackt)."""
    what = what or tr("{ext}-Datei", ext=".lp5")
    try:
        z = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as e:
        raise ValueError(tr("Keine gültige {what} ({e})", what=what, e=e)) from e
    with z:
        infos = z.infolist()
        members = [(info, member_parts(info.filename)) for info in infos]
        if sum(info.file_size for info in infos) > MAX_UNPACKED:
            raise ValueError(tr("Archiv ist entpackt zu groß"))
        root = dest.resolve()
        for info, parts in members:
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if not target.resolve().is_relative_to(root):
                raise ValueError(tr("Unsicherer Pfad im Archiv: {name}", name=info.filename))
            if info.is_dir() or info.filename.endswith("\\"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with z.open(info) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
            except ARCHIVE_ERRORS as e:  # Pruefsumme, Kompression, Verschluesselung
                raise ValueError(tr("Archiv beschädigt oder nicht unterstützt: {name} ({e})",
                                 name=info.filename, e=e)) from e
