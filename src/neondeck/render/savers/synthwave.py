"""Synthwave: Retro-Sonne mit Streifen, laufendes Gitter, Berge; Neon-Pink/Violett."""
from __future__ import annotations

import math
import random
from datetime import datetime

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ...core.i18n import N_
from ...device.layout import WHEEL_SIZE
from ..draw import mix, to_round
from ..fonts import font
from ..palette import hex_rgb
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver
from .tiles import MinuteCache, centered, clock_digits, tile_texts


class SynthwaveSaver(Saver):
    name, label = "synthwave", N_("Synthwave")
    HORIZON = 168

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._sky = self._make_sky()
        self._clock = MinuteCache(lambda now: tile_texts(
            clock_digits(now, 2, 56, hex_rgb("#2de2e6"), "Orbitron"), glow=4))  # HH MM, untere Reihe

    def _make_sky(self) -> Image.Image:
        top, bottom = np.array(hex_rgb("#0b0221"), float), np.array(hex_rgb("#7a1fa2"), float)
        ys = np.linspace(0, 1, self.HORIZON)[:, None]
        rows = top + (bottom - top) * ys ** 1.6
        sky = np.repeat(rows[:, None, :], WIDTH, axis=1)
        img = Image.new("RGB", (WIDTH, HEIGHT), hex_rgb("#090014"))
        img.paste(Image.fromarray(sky.astype(np.uint8), "RGB"), (0, 0))
        d = ImageDraw.Draw(img)
        rng = random.Random(7)
        for _ in range(70):
            x, y = rng.randrange(WIDTH), rng.randrange(self.HORIZON - 40)
            v = rng.randrange(120, 255)
            d.point((x, y), fill=(v, v, min(255, v + 30)))
        return img

    def _sun(self, size: int, t: float) -> tuple[Image.Image, Image.Image]:
        """Sonne mit Verlauf Gelb → Pink und nach oben wandernden Streifen."""
        ys = np.linspace(0, 1, size)[:, None, None]
        top, bottom = np.array(hex_rgb("#ffd319"), float), np.array(hex_rgb("#ff2975"), float)
        grad = np.repeat(top + (bottom - top) * ys, size, axis=1).astype(np.uint8)
        sun = Image.fromarray(grad, "RGB")
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, size - 1, size - 1), fill=255)
        phase = (t * 6) % 12
        y = size * 0.5 + phase
        gap = 2.0
        while y < size:
            md.rectangle((0, int(y), size, int(y + gap)), fill=0)
            y += 12
            gap += 1.2
        return sun, mask

    def frame(self, t: float) -> Frame:
        img = self._sky.copy()
        sun, mask = self._sun(150, t)
        img.paste(sun, (WIDTH // 2 - 75, self.HORIZON - 120), mask)
        d = ImageDraw.Draw(img)
        # Berge
        rng = random.Random(3)
        pts = [(0, self.HORIZON)]
        pts.extend((x, self.HORIZON - rng.randrange(8, 46)) for x in range(0, WIDTH + 30, 30))
        pts.append((WIDTH, self.HORIZON))
        d.polygon(pts, fill=hex_rgb("#12002a"), outline=hex_rgb("#ff2a6d"))
        d.rectangle((0, self.HORIZON, WIDTH, HEIGHT), fill=hex_rgb("#090014"))
        # Gitter: Fluchtlinien und nach vorn laufende Querlinien
        vx, grid = WIDTH / 2, hex_rgb("#ff2a6d")
        for i in range(-12, 13):
            d.line((vx + i * 6, self.HORIZON, vx + i * 90, HEIGHT), fill=grid)
        phase = (t * 0.8) % 1.0
        for n in range(12):
            z = (n + 1 - phase)
            y = self.HORIZON + (HEIGHT - self.HORIZON) * (1 / max(0.3, 12 - z * 0.95)) * 1.6
            if self.HORIZON < y < HEIGHT:
                k = (y - self.HORIZON) / (HEIGHT - self.HORIZON)
                d.line((0, y, WIDTH, y), fill=mix(hex_rgb("#3a0a4a"), grid, 0.3 + 0.7 * k))
        d.line((0, self.HORIZON, WIDTH, self.HORIZON), fill=hex_rgb("#ff8bd0"), width=2)
        now = self._now()
        img = ImageChops.add(img, self._clock.get(now))
        wheel = self._wheel(t, now)
        pulse = 0.55 + 0.45 * math.sin(t * 1.6)
        leds = {code: mix(hex_rgb("#7a1fa2"), hex_rgb("#ff2975"), pulse if i % 2 else 1 - pulse)
                for i, code in enumerate(LED_CODES)}
        return Frame(img, wheel, leds)

    def _wheel(self, t: float, now: datetime) -> Image.Image:
        img = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), hex_rgb("#0b0221"))
        sun, mask = self._sun(200, t)
        img.paste(sun, (20, 20), mask)
        d = ImageDraw.Draw(img)
        centered(d, (WHEEL_SIZE / 2, 96), now.strftime("%H:%M"), font(40, True, "Orbitron"),
                  hex_rgb("#0b0221"))
        return to_round(img)
