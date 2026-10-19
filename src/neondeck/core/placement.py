"""Fenster platzieren: „das nächste Fenster von App X kommt nach Ziel Y“ (Qt-frei).

Eine Aktion (``run``, ``app_focus``, ``terminal_layout``) meldet vor dem Start
``PlacementBook.expect(app, Bildschirm, Platz)``. Sobald KWin ein neues Fenster meldet, fragt
das KWin-Skript beim Dienst nach (``placement(resourceClass, desktopFileName, pid)``); der
Dienst gibt den ersten passenden, noch nicht abgelaufenen Wunsch zurück und streicht ihn. Die
Geometrie (Bildschirm finden, Hälften/Viertel der Arbeitsfläche) rechnet das KWin-Skript, das
die Bildschirme kennt. Ereignisgesteuert: niemand fragt im Takt.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

EXPECT_S = 15.0  # so lange wartet ein Wunsch auf sein Fenster
# Platz auf dem Bildschirm (Arbeitsfläche ohne Leisten); "none" = Groesse behalten
PLACES = ["none", "maximize", "left", "right", "top", "bottom",
          "top_left", "top_right", "bottom_left", "bottom_right"]
# Bildschirm nach Lage (das KWin-Skript rechnet sie aus den Geometrien aus)
SCREEN_POSITIONS = ("left", "center", "right", "top", "bottom")
SCREEN_ALIASES = {"links": "left", "mitte": "center", "rechts": "right", "oben": "top",
                  "unten": "bottom"}


def normalize_screen(screen: object) -> str:
    """Bildschirm-Angabe: Ausgangsname (``DP-3``) unveraendert, Lagen auch deutsch
    (``links`` -> ``left``); leer = aktueller Bildschirm des Fensters."""
    text = str(screen or "").strip()
    low = text.lower()
    if low in SCREEN_POSITIONS:
        return low
    return SCREEN_ALIASES.get(low, text)


def normalize_place(place: object) -> str:
    text = str(place or "none").strip().lower()
    return text if text in PLACES else "none"


def app_key_of(argv: list[str]) -> str:
    """Kennung der App eines Startbefehls: Programmname, bei ``flatpak run`` die App-ID."""
    if not argv:
        return ""
    if Path(argv[0]).name == "flatpak" and "run" in argv:
        rest = argv[argv.index("run") + 1:]
        return next((a for a in rest if not a.startswith("-")), "")
    return Path(argv[0]).name


def window_matches(key: str, resource_class: str, desktop_file: str) -> bool:
    """Passt ein neues Fenster zur App ``key``? Gross/klein egal; ``konsole`` passt auch auf
    ``org.kde.konsole`` (Wayland meldet die Desktop-ID als Klasse), ``.desktop`` zaehlt nicht."""
    key = key.lower().removesuffix(".desktop")
    if not key:
        return False
    for name in (resource_class.lower(), desktop_file.lower().removesuffix(".desktop")):
        if name and (name == key or name.endswith("." + key) or key.endswith("." + name)):
            return True
    return False


@dataclass
class Ticket:
    """Ein Platzierungswunsch; ``wait`` kehrt zurueck, sobald KWin das Fenster gemeldet hat."""

    key: str
    screen: str
    place: str
    deadline: float
    pid: int = 0  # Prozess des Starts (nach dem Start eingetragen), passt zusaetzlich
    done: threading.Event = field(default_factory=threading.Event)

    def wait(self, timeout: float) -> bool:
        return self.done.wait(timeout)

    def bind_pid(self, pid: int) -> None:
        """Prozess des Starts eintragen (das Fenster passt dann auch ueber die PID)."""
        self.pid = pid

    def abandon(self) -> None:
        """Start gescheitert: der Wunsch verfaellt (beim naechsten ``claim`` gestrichen)."""
        self.deadline = 0.0

    def reply(self) -> dict:
        return {"screen": self.screen, "place": self.place}


class PlacementBook:
    """Offene Wuensche in Reihenfolge; Aufrufe aus Aktions-Threads und dem GUI-Thread."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._open: list[Ticket] = []

    def expect(self, key: str, screen: object = "", place: object = "none", *,
               pid: int = 0) -> Ticket | None:
        """Wunsch anlegen; ``None``, wenn es nichts zu tun gibt (kein Platz, kein Bildschirm)
        oder keine App-Kennung bekannt ist."""
        screen, place = normalize_screen(screen), normalize_place(place)
        if not key or (place == "none" and not screen):
            return None
        ticket = Ticket(key, screen, place, self._clock() + EXPECT_S, pid)
        with self._lock:
            self._open.append(ticket)
        return ticket

    def cancel(self, ticket: Ticket | None) -> None:
        with self._lock:
            if ticket in self._open:
                self._open.remove(ticket)

    def claim(self, resource_class: str, desktop_file: str, pid: int) -> Ticket | None:
        """Erster offener Wunsch fuer dieses neue Fenster (gleicher Prozess vor gleicher
        App); er wird gestrichen und sein ``wait`` kehrt zurueck."""
        now = self._clock()
        with self._lock:
            self._open = [t for t in self._open if t.deadline > now]
            hit = next((t for t in self._open if pid and t.pid == pid), None)
            if hit is None:
                hit = next((t for t in self._open
                            if window_matches(t.key, resource_class, desktop_file)), None)
            if hit is not None:
                self._open.remove(hit)
        if hit is not None:
            hit.done.set()
        return hit

    def pending(self) -> list[Ticket]:
        with self._lock:
            return list(self._open)
