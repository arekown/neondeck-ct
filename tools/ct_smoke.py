"""Hardware-Probe fuer den Loupedeck CT (nur am echten Geraet ausfuehren).

/usr/bin/python3 tools/ct_smoke.py
Verbindet, druckt die Seriennummer, fuellt alle Displays mit Testfarben,
faerbt die LEDs der runden Tasten in 8 Farben und druckt 30 s lang Ereignisse.
"""
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neondeck.device.ct import CTDevice
from neondeck.device.discovery import find_ct
from neondeck.device.layout import ROUND_FIRST, Display

DISPLAY_COLORS = {
    Display.LEFT: (255, 0, 0),      # rot
    Display.CENTER: (0, 255, 0),    # gruen
    Display.RIGHT: (0, 0, 255),     # blau
    Display.WHEEL: (255, 160, 0),   # orange
}
LED_COLORS = [
    ("rot", (255, 0, 0)), ("orange", (255, 128, 0)), ("gelb", (255, 255, 0)),
    ("gruen", (0, 255, 0)), ("tuerkis", (0, 255, 255)), ("blau", (0, 0, 255)),
    ("violett", (160, 0, 255)), ("weiss", (255, 255, 255)),
]
LISTEN_SECONDS = 30


def fill(display: Display, rgb: tuple[int, int, int]) -> bytes:
    r, g, b = rgb
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return struct.pack(">H" if display.big_endian else "<H", v) * (display.width * display.height)


def main() -> int:
    port = find_ct()
    print(f"Gerät: {port or 'nicht gefunden'}")
    if not port:
        return 1
    up = threading.Event()
    dev = CTDevice(
        port_finder=lambda: port,
        on_event=lambda ev: print(f"{time.strftime('%H:%M:%S')} {ev}", flush=True),
        on_state=lambda c: (print("verbunden" if c else "getrennt", flush=True), c and up.set()),
    )
    dev.start()
    try:
        if not up.wait(5):
            print("Keine Verbindung binnen 5 s")
            return 1
        print(f"Seriennummer: {dev.serial_number(timeout=2)}")
        dev.set_brightness(10)
        for display, rgb in DISPLAY_COLORS.items():
            dev.draw(display, fill(display, rgb))
            print(f"Display {display.name} ({display.id}): RGB {rgb}")
        leds = {ROUND_FIRST + i: rgb for i, (_, rgb) in enumerate(LED_COLORS)}
        dev.set_leds(leds)
        for i, (name, _) in enumerate(LED_COLORS):
            print(f"LED Code {ROUND_FIRST + i} (runde Taste {i + 1} von links?): {name}")
        print(f"{LISTEN_SECONDS} s Ereignisse – Tasten drücken, Regler drehen, Displays berühren …",
              flush=True)
        time.sleep(LISTEN_SECONDS)
    finally:
        dev.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
