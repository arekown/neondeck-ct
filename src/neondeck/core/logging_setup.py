"""Logging: Datei (1 MB x 3) im Zustandsverzeichnis und stderr."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_MARK = "_neondeck"


def setup(level: int = logging.INFO, filename: str = "log.txt") -> list[logging.Handler]:
    """Richtet das Wurzel-Logging ein (wiederholbar, ohne doppelte Handler).

    Jeder Prozess schreibt in eine eigene Datei (``filename``), damit sich die Rotation
    von Dienst und Editor nicht in die Quere kommt."""
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(h)
        h.close()
    directory = paths.state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(directory / filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                            encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]
    fmt = logging.Formatter(LOG_FORMAT)
    for h in handlers:
        setattr(h, _MARK, True)
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(level)
    return handlers
