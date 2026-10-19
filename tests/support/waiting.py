"""Ereignisbasiertes Warten fuer Tests (robust unter Rechnerlast).

Tests warten nie eine feste Zeit auf etwas, das passieren soll, sondern auf die Bedingung
selbst; die Obergrenze zaehlt nur im Fehlerfall und ist deshalb grosszuegig (ein voll
ausgelasteter Rechner darf einen Test verlangsamen, aber nicht rot machen).
"""
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

TIMEOUT = 15.0  # nur im Fehlerfall erreicht


def wait_until(cond: Callable[[], object], timeout: float = TIMEOUT,
               step: float = 0.01) -> bool:
    """Bis ``cond()`` wahr ist (``True``) oder ``timeout`` Sekunden um sind (``False``);
    die Qt-Ereignisschleife laeuft dabei weiter (Sockets, Timer, Signale aus Threads)."""
    end = time.monotonic() + timeout
    while True:
        QApplication.processEvents()
        if cond():
            return True
        if time.monotonic() >= end:
            return False
        QTest.qWait(max(1, round(step * 1000)))
