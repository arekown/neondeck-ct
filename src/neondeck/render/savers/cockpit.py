"""Cockpit-HUD im Stil des Cyberpunk-Cockpit-Themes: Raster, abgeschraegte Kachelrahmen ueber
dem Touch-Raster, Leuchtuhr, Scan-Linie, echte CPU-/RAM-Anzeige, Radar auf dem Rad."""
from __future__ import annotations

import math
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw

from ...core.i18n import N_, tr
from ...core.sysload import CpuMeter
from ...device.layout import FIELD_SIZE as TILE
from ...device.layout import STRIP_WIDTH as STRIP
from ...device.layout import WHEEL_SIZE
from ..draw import bevel, mix, scale, to_round
from ..fonts import font
from ..palette import (
    C_BG,
    C_CYAN,
    C_CYAN_DIM,
    C_MAGENTA,
    C_MAGENTA_DIM,
    C_MUTED,
    C_TEXT,
    C_YELLOW,
    RGB,
)
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver
from .tiles import MinuteCache, TileText, centered, clock_digits, date_tiles, tile_texts


class CockpitSaver(Saver):
    name, label = "cockpit", N_("Cockpit-HUD")

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._base = self._background()
        self._wheel_base = self._radar_base()
        self._meter = CpuMeter()
        self._meter_at = -1.0
        self._cpu = self._mem = 0.0
        self._clock = MinuteCache(self._clock_layer)
        self._pings: list[tuple[int, float]] = []  # (Kachel, Startzeit)
        self._next_ping = 0.0
        self._stream = [self._hexline() for _ in range(20)]
        self._stream_at = 0.0
        self._blips: list[tuple[float, float, float]] = []  # (Winkel, Radius, Zeit)

    def _hexline(self) -> str:
        return "".join(self.rng.choice("0123456789ABCDEF") for _ in range(4))

    def _background(self) -> Image.Image:
        img = Image.new("RGB", (WIDTH, HEIGHT), C_BG)
        d = ImageDraw.Draw(img)
        grid = mix(C_BG, C_CYAN, 0.10)
        for x in range(0, WIDTH, 40):
            d.line((x, 0, x, HEIGHT), fill=grid)
        for y in range(0, HEIGHT, 40):
            d.line((0, y, WIDTH, y), fill=grid)
        frame = mix(C_BG, C_CYAN_DIM, 0.55)
        for row in range(3):
            for col in range(4):
                x0, y0 = STRIP + col * TILE + 6, row * TILE + 6
                d.polygon(bevel(x0, y0, x0 + TILE - 12, y0 + TILE - 12, 12), outline=frame)
        d.line((STRIP - 1, 0, STRIP - 1, HEIGHT), fill=mix(C_BG, C_CYAN, 0.35))
        d.line((WIDTH - STRIP, 0, WIDTH - STRIP, HEIGHT), fill=mix(C_BG, C_CYAN, 0.35))
        return img

    def _radar_base(self) -> Image.Image:
        img = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), C_BG)
        d = ImageDraw.Draw(img)
        c = WHEEL_SIZE / 2
        for r in (110, 80, 50, 20):
            d.ellipse((c - r, c - r, c + r, c + r), outline=mix(C_BG, C_CYAN_DIM, 0.7))
        d.line((c, 10, c, WHEEL_SIZE - 10), fill=mix(C_BG, C_CYAN_DIM, 0.4))
        d.line((10, c, WHEEL_SIZE - 10, c), fill=mix(C_BG, C_CYAN_DIM, 0.4))
        for i in range(60):
            a = math.radians(i * 6)
            r0 = 112 if i % 5 else 104
            d.line((c + r0 * math.cos(a), c + r0 * math.sin(a),
                    c + 118 * math.cos(a), c + 118 * math.sin(a)),
                   fill=C_CYAN if i % 5 == 0 else C_CYAN_DIM)
        return img

    @staticmethod
    def _clock_layer(now: datetime) -> Image.Image:
        """Reihe 1: Datum, Reihe 2: HH MM (leuchtend), je Feld."""
        return ImageChops.add(
            tile_texts(date_tiles(now, 0, 30, C_TEXT, "Rajdhani", bold=True)),
            tile_texts(clock_digits(now, 1, 74, C_CYAN, "Orbitron"), glow=6))

    def frame(self, t: float) -> Frame:
        now = self._now()
        img = self._base.copy()
        d = ImageDraw.Draw(img)
        # Kachel-Pings: zufaellig aufleuchtende Rahmen in Magenta
        if t >= self._next_ping:
            self._pings.append((self.rng.randrange(12), t))
            self._next_ping = t + self.rng.uniform(0.5, 1.2)
        self._pings = [(i, s) for i, s in self._pings if t - s < 1.6]
        for i, s in self._pings:
            k = 1.0 - (t - s) / 1.6
            col, row = i % 4, i // 4
            x0, y0 = STRIP + col * TILE + 6, row * TILE + 6
            pts = bevel(x0, y0, x0 + TILE - 12, y0 + TILE - 12, 12)
            d.polygon(pts, fill=mix(C_BG, C_MAGENTA_DIM, 0.25 * k),
                      outline=mix(C_BG, C_MAGENTA, k))
        # Uhr und Datum je Feld (aufaddiert, damit das Leuchten ueber dem Raster liegt);
        # unten links Status, unten rechts Sekunden
        img = ImageChops.add(img, self._clock.get(now))
        img = ImageChops.add(img, tile_texts([
            TileText(0, 2, tr("IDLE"), 20, C_MUTED, "Share Tech Mono"),
            TileText(3, 2, f"{now.second:02d}", 40, C_MAGENTA, "Share Tech Mono")]))
        d = ImageDraw.Draw(img)
        # Scan-Linie mit Schweif
        y = (t * 70) % (HEIGHT + 60) - 30
        for k in range(14):
            yy = int(y - k * 2)
            if 0 <= yy < HEIGHT:
                d.line((STRIP, yy, WIDTH - STRIP - 1, yy),
                       fill=mix(C_BG, C_CYAN, 0.55 * (1 - k / 14)))
        self._strips(d, t)
        wheel = self._radar(t, now)
        return Frame(img, wheel, self._leds(t))

    def _strips(self, d: ImageDraw.ImageDraw, t: float) -> None:
        if t - self._meter_at >= 1.0:
            self._meter.update()
            self._meter_at = t
        self._cpu += (self._meter.cpu - self._cpu) * 0.25
        self._mem += (self._meter.mem - self._mem) * 0.25
        small = font(13, True, "Share Tech Mono")
        for x, label, value, color in ((6, "CPU", self._cpu, C_CYAN),
                                       (32, "RAM", self._mem, C_MAGENTA)):
            d.text((x + 11, 12), label, font=small, fill=C_MUTED, anchor="mm")
            segments = 20
            lit = round(value * segments)
            for s in range(segments):
                y1 = HEIGHT - 26 - s * 11
                on = s < lit
                c = (C_YELLOW if s >= 16 else color) if on else mix(C_BG, color, 0.15)
                d.rectangle((x, y1 - 8, x + 21, y1), fill=c)
            d.text((x + 11, HEIGHT - 10), f"{round(value * 100):d}", font=small, fill=color,
                   anchor="mm")
        # rechts: laufender Datenstrom
        if t - self._stream_at >= 0.15:
            self._stream.insert(0, self._hexline())
            self._stream.pop()
            self._stream_at = t
        for n, line in enumerate(self._stream):
            d.text((WIDTH - 30, 10 + n * 13), line, font=small,
                   fill=C_MAGENTA if n == 0 else mix(C_BG, C_CYAN, 1.0 - n / 22), anchor="mm")

    def _radar(self, t: float, now: datetime) -> Image.Image:
        img = self._wheel_base.copy()
        d = ImageDraw.Draw(img)
        c = WHEEL_SIZE / 2
        angle = (t * 90) % 360  # eine Umdrehung in 4 s
        for k in range(24):
            a0 = angle - (k + 1) * 2.5
            d.pieslice((c - 108, c - 108, c + 108, c + 108), a0, a0 + 2.6,
                       fill=mix(C_BG, C_CYAN, 0.45 * (1 - k / 24)))
        if self.rng.random() < 0.04:
            self._blips.append((self.rng.uniform(0, 360), self.rng.uniform(25, 100), t))
        self._blips = [b for b in self._blips if t - b[2] < 3]
        for a, r, s in self._blips:
            k = 1 - (t - s) / 3
            x = c + r * math.cos(math.radians(a))
            y = c + r * math.sin(math.radians(a))
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=mix(C_BG, C_MAGENTA, k))
        d.line((c, c, c + 108 * math.cos(math.radians(angle)),
                c + 108 * math.sin(math.radians(angle))), fill=C_CYAN, width=2)
        d.ellipse((c - 30, c - 22, c + 30, c + 22), fill=C_BG)
        centered(d, (c, c), f"{now.second:02d}", font(30, True, "Orbitron"), C_CYAN)
        return to_round(img)

    @staticmethod
    def _leds(t: float) -> dict[int, RGB]:
        pos = (t * 3) % 8
        out = {}
        for i, code in enumerate(LED_CODES):
            dist = min(abs(i - pos), 8 - abs(i - pos))
            out[code] = C_MAGENTA if dist < 0.5 else scale(C_CYAN, max(0.12, 0.6 - dist * 0.2))
        return out
