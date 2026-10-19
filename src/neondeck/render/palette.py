"""Farben der Anzeigen: Cockpit-Palette, Werte-/Fehlerfarben (RGB-Tupel und ``#rrggbb``)."""
from __future__ import annotations

RGB = tuple[int, int, int]


def hex_rgb(c: str) -> RGB:
    """``#rrggbb`` -> RGB."""
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb_hex(c: RGB) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


# --- Cockpit (HUD im Stil des Cyberpunk-Cockpit-Themes) ---------------------------------
C_BG, C_BG2 = hex_rgb("#06080f"), hex_rgb("#0a0e1a")
C_CYAN, C_CYAN_DIM = hex_rgb("#05d9e8"), hex_rgb("#0792a0")
C_MAGENTA, C_MAGENTA_DIM = hex_rgb("#ff2a6d"), hex_rgb("#b81e4f")
C_YELLOW, C_OK = hex_rgb("#f9f002"), hex_rgb("#00ff9f")
C_TEXT, C_MUTED = hex_rgb("#cfeef2"), hex_rgb("#5f7d86")

# --- Klassisch: Tasten, Leisten, Rad ----------------------------------------------------
ERROR: RGB = (255, 32, 32)      # Fehlerblitz und Fehlerrahmen (die Engine blitzt in ERROR_HEX)
ERROR_HEX = rgb_hex(ERROR)
BADGE_COLOR = "#e8b84a"         # Ordner-Kennzeichen
BACK_COLOR = "#e2e2e2"          # Pfeil der „Zurück“-Kachel (wie die Aktions-Icons)
VALUE_COLOR = "#7fd0ff"         # Werte in Leiste und Rad (Text, Balken, Bogen)
TRACK_COLOR = "#333333"         # leere Spur von Balken und Bogen
MUTED_COLOR = "#6a6a6a"         # Rad-Bogen, wenn stumm
