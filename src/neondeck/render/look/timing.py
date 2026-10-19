"""Takt des Cockpit-Looks: Bildnummer statt Uhr, Kachel-Pings.

Die Animation laeuft ueber eine Bildnummer (``FPS`` Bilder je Sekunde Animationszeit): gleiche
Nummer, gleiches Bild – die Engine sendet dann nichts. Auch Pings und Funkeln haengen nur von
der Bildnummer ab. Leisten und Rad aendern sich nur alle ``SLOW_EVERY`` Bilder.
"""
from __future__ import annotations

import random

FPS = 6                 # Ziel: hoechstens so viele Bilder je Sekunde
FRAME_S = 1 / FPS
SLOW_EVERY = 3          # Leisten-Lauflicht und Rad-Ring: jedes dritte Bild (2 je Sekunde)
FIELDS = 12
PING_EVERY = 5          # alle 5 Bilder ein neuer Ping …
PING_LEN = 9            # … der 1,5 s abklingt


def slow_step(frame: int) -> int:
    """Stufe fuer Leisten und Rad: aendert sich nur alle ``SLOW_EVERY`` Bilder."""
    return frame // SLOW_EVERY


def ping_tiles(frame: int) -> list[tuple[int, float]]:
    """Aktive Kachel-Pings zur Bildnummer: ``(Feld, Staerke 0–1)``; nur von ``frame``
    abhaengig (gleiches Bild, gleiche Pings)."""
    out = []
    last = frame // PING_EVERY
    for n in range(max(0, (frame - PING_LEN) // PING_EVERY), last + 1):
        age = frame - n * PING_EVERY
        if 0 <= age < PING_LEN:
            out.append((random.Random(n * 7919 + 13).randrange(FIELDS), 1 - age / PING_LEN))
    return out
