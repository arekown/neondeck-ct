"""Fenster nach vorn holen: kurzes Einmal-Skript in KWin (``data/kwin/focus.js``), das
sofort wieder entladen wird."""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

from ..core import paths
from ..core.fileio import runtime_tempfile
from ..core.windows import WindowInfo
from .kwin_scripts import KWinScripts

log = logging.getLogger(__name__)

FOCUS_SCRIPT_NAME = "neondeck-ct-focus"


def focus_template() -> Path:
    """Skriptvorlage; ``__ID__`` = Fenster-ID, ``__APP__`` = App (je als JSON-Text)."""
    return paths.bundled_dir() / "kwin" / "focus.js"


def focus_script(template: str, window_id: str, app: str) -> str:
    """Vorlage mit eingesetzter Fenster-ID und App (JSON-Text; ein ``%`` im Skript stoert
    nicht, ein Platzhalter im eingesetzten Text wird nicht noch einmal ersetzt)."""
    values = {"__ID__": json.dumps(window_id), "__APP__": json.dumps(app)}
    return re.sub("__ID__|__APP__", lambda m: values[m.group(0)], template)


class WindowFocus:
    """Aufrufe aus Aktions-Threads (blockierende D-Bus-Aufrufe nie im GUI-Thread);
    gleichzeitige laufen nacheinander (ein Einmal-Skriptname). Aus fremden Threads gehen nur
    Methodenaufrufe ueber den Bus; Objekt und Dienst meldet der Waechter im GUI-Thread an."""

    def __init__(self, scripts: KWinScripts) -> None:
        self._scripts = scripts
        self._lock = threading.Lock()

    def focus(self, target: WindowInfo, app_id: str) -> bool:
        """``target`` aktivieren (ist es weg, das erste Fenster der App ``app_id``);
        ``False``, wenn das Skript nicht lief."""
        app = (app_id or target.app_key).lower()  # nie leer: passte sonst auf Fenster ohne Namen
        with self._lock:
            try:
                text = focus_script(focus_template().read_text(encoding="utf-8"),
                                    target.internal_id, app)
                path = runtime_tempfile("neondeck-ct-focus-", ".js", text)
            except OSError as e:
                log.warning("Fokus-Skript nicht angelegt: %s", e)
                return False
            try:
                sid = self._scripts.load(path, FOCUS_SCRIPT_NAME)
                # run wertet das Skript aus, bevor KWin den naechsten Aufruf bearbeitet
                # (belegt 18.10.2026 an KWin 6.7.5) -> sofort wieder entladen
                self._scripts.unload(FOCUS_SCRIPT_NAME)
            finally:
                path.unlink(missing_ok=True)
        if sid is None:
            log.warning("Fokus-Skript für %s nicht geladen", app_id or target.internal_id)
            return False
        return True
