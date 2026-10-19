"""Stoppuhr einer Kachel (Aktion ``stopwatch``); die Engine haelt je Bedienelement eine."""
from __future__ import annotations

LONG_PRESS_S = 1.0


class Stopwatch:
    """Druecken startet/stoppt, ein Druck laenger als 1 s setzt zurueck. Zeiten sind
    Epochen-Sekunden (``time.time()``), dieselbe Uhr wie ``live_image`` (``now.timestamp()``)."""

    def __init__(self):
        self.running = False
        self._start = 0.0
        self._elapsed = 0.0

    def press(self, duration_s: float, now: float) -> None:
        if duration_s > LONG_PRESS_S:
            self.running = False
            self._elapsed = 0.0
        elif self.running:
            self._elapsed += now - self._start
            self.running = False
        else:
            self._start = now
            self.running = True

    def elapsed(self, now: float) -> float:
        return self._elapsed + (now - self._start if self.running else 0.0)

    def display(self, now: float) -> str:
        total = int(self.elapsed(now))
        h, rest = divmod(total, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
