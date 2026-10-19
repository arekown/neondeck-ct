"""Die Audio-Werkzeuge an einer Stelle: ``pactl`` (PipeWire-Pulse) fuer Stumm, Ausgaenge,
Anwendungen und den Stumm-Zustand (``desktop.audio_state``), ``wpctl`` (WirePlumber) nur fuer
die Lautstaerke des Standardausgangs – Standardgeraete, Befehle und das Lesen der Ausgabe
(ohne Qt).

Die Lautstaerke des Standardausgangs aendert ``wpctl set-volume -l`` relativ mit Obergrenze in
einem Aufruf: Schnelles Drehen und zwei Regler auf derselben Senke verlieren keinen Schritt,
und die Lautstaerke geht nie, auch nicht kurz, ueber ``MAX_PERCENT`` (``pactl`` kennt keine
Grenze). ``wpctl get-volume`` liefert Wert und Stumm-Zustand zusammen: zwei Aufrufe je Schritt.

Belegt am 18.10.2026 (pactl 17.0, PipeWire): die Ausgabe ist uebersetzt („Mute: nein“),
``get-sink-volume`` nennt je Kanal ``… /  42% / …`` (der erste Kanal zaehlt). ``wpctl
get-volume`` antwortet ``Volume: 0.42`` bzw. ``Volume: 0.42 [MUTED]`` (unuebersetzt).
"""
from __future__ import annotations

import re

from ..core.proc import PACTL, WPCTL

SINK = "@DEFAULT_SINK@"      # Standardausgang
SOURCE = "@DEFAULT_SOURCE@"  # Standardeingang (Mikrofon)
WP_SINK = "@DEFAULT_AUDIO_SINK@"  # Standardausgang fuer ``wpctl``
VOLUME_STEP = 2   # Prozent je Drehschritt
MAX_PERCENT = 100  # hoeher dreht ein Regler nicht (relativ waere mehr moeglich)
_WP_VOLUME = re.compile(r"Volume:\s*([0-9.]+)")
# Stumm-Zustand lesen: Art (Zustandsquelle) -> pactl-Argumente
MUTE_READS = {"mute": ["get-sink-mute", SINK], "mic_mute": ["get-source-mute", SOURCE]}
_PERCENT = re.compile(r"(\d+)\s*%")


def argv(*args: str) -> list[str]:
    return [PACTL, *args]


def volume_delta(steps: int) -> str:
    """Relative Aenderung fuer ``steps`` Drehschritte, z. B. ``+6%``."""
    return f"{'+' if steps > 0 else '-'}{abs(steps) * VOLUME_STEP}%"


def sink_volume_change(steps: int) -> list[str]:
    """Standardausgang um ``steps`` Drehschritte, hoechstens ``MAX_PERCENT`` (``wpctl``)."""
    delta = f"{abs(steps) * VOLUME_STEP}%{'+' if steps > 0 else '-'}"
    return [WPCTL, "set-volume", "-l", f"{MAX_PERCENT / 100:.1f}", WP_SINK, delta]


def sink_volume_read() -> list[str]:
    """Lautstaerke und Stumm-Zustand des Standardausgangs lesen (``wpctl``)."""
    return [WPCTL, "get-volume", WP_SINK]


def parse_sink_volume(text: str) -> tuple[int | None, bool]:
    """``(Prozent | None, stumm)`` aus ``wpctl get-volume``."""
    m = _WP_VOLUME.search(text)
    return (round(float(m.group(1)) * 100) if m else None), "[MUTED]" in text


def parse_percent(text: str) -> int | None:
    """Erster Prozentwert (``42%``) einer Ausgabe; ``None`` ohne."""
    m = _PERCENT.search(text)
    return int(m.group(1)) if m else None


def parse_mute(text: str) -> bool | None:
    """``Mute: yes`` -> True, ``Mute: no`` -> False, sonst ``None`` (auch uebersetzt)."""
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == "mute":
            v = value.strip().lower()
            if v in ("yes", "ja"):
                return True
            if v in ("no", "nein"):
                return False
    return None
