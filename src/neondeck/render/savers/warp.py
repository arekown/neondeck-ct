"""Warp: Sternenflug aus der Mitte heraus, Tunnelringe auf dem Rad."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ...core.i18n import N_
from ...device.layout import WHEEL_SIZE
from ..draw import mix, scale, to_round
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver


class WarpSaver(Saver):
    name, label = "warp", N_("Sternenflug")
    STARS = 220

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._stars = [self._star(far=False) for _ in range(self.STARS)]
        self._last = 0.0

    def _star(self, far: bool = True) -> list[float]:
        return [self.rng.uniform(-1, 1), self.rng.uniform(-1, 1),
                self.rng.uniform(0.7, 1.0) if far else self.rng.uniform(0.05, 1.0),
                self.rng.random()]

    def frame(self, t: float) -> Frame:
        dt = min(0.2, max(0.0, t - self._last))
        self._last = t
        speed = 0.35 + 0.25 * math.sin(t * 0.3)
        img = Image.new("RGB", (WIDTH, HEIGHT), (2, 3, 10))
        d = ImageDraw.Draw(img)
        cx, cy, f = WIDTH / 2, HEIGHT / 2, 180
        for s in self._stars:
            z0 = s[2]
            s[2] -= speed * dt
            if s[2] <= 0.02:
                s[:] = self._star()
                continue
            x0, y0 = cx + s[0] / z0 * f, cy + s[1] / z0 * f
            x1, y1 = cx + s[0] / s[2] * f, cy + s[1] / s[2] * f
            if not (0 <= x1 < WIDTH and 0 <= y1 < HEIGHT):
                s[:] = self._star()
                continue
            k = min(1.0, (1 - s[2]) * 1.4)
            tint = mix((150, 180, 255), (255, 255, 255), s[3])
            d.line((x0, y0, x1, y1), fill=scale(tint, k), width=2 if s[2] < 0.25 else 1)
        wheel = self._tunnel(t)
        pulse = 0.5 + 0.5 * math.sin(t * 2)
        leds = {code: mix((20, 40, 120), (200, 220, 255), pulse if i % 2 else 1 - pulse)
                for i, code in enumerate(LED_CODES)}
        return Frame(img, wheel, leds)

    def _tunnel(self, t: float) -> Image.Image:
        img = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), (2, 3, 10))
        d = ImageDraw.Draw(img)
        c = WHEEL_SIZE / 2
        for n in range(10):
            r = ((n + (t * 1.5) % 1.0) / 10) ** 2 * 130
            k = r / 130
            d.ellipse((c - r, c - r, c + r, c + r),
                      outline=mix((20, 40, 120), (190, 210, 255), k), width=2)
        return to_round(img)
