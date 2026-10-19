"""Matrix: fallende Zeichen in Gruen."""
from __future__ import annotations

import random

import numpy as np
from PIL import Image, ImageDraw

from ...core.i18n import N_
from ...device.layout import WHEEL_SIZE
from ..draw import to_round
from ..fonts import font
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver

GLYPHS = "0123456789ABCDEFZ:=+*<>|#$%&ΣΔΩλπ"


class _Rain:
    def __init__(self, rng: random.Random, w: int, h: int, cell: int) -> None:
        self.rng, self.w, self.h, self.cell = rng, w, h, cell
        self.cols = w // cell
        self.heads = [rng.uniform(-h, 0) for _ in range(self.cols)]
        self.speed = [rng.uniform(60, 160) for _ in range(self.cols)]
        self.img = Image.new("RGB", (w, h), (0, 0, 0))
        self.fnt = font(cell + 2, True, "Share Tech Mono")
        self._last = 0.0

    def step(self, t: float) -> Image.Image:
        dt = min(0.2, max(0.0, t - self._last))
        self._last = t
        a = np.asarray(self.img, dtype=np.float32) * (0.86 ** (dt * 20))
        self.img = Image.fromarray(a.astype(np.uint8), "RGB")
        d = ImageDraw.Draw(self.img)
        for c in range(self.cols):
            before = self.heads[c]
            self.heads[c] += self.speed[c] * dt
            y0 = int(before // self.cell) * self.cell
            for y in range(y0, int(self.heads[c]) + 1, self.cell):
                if 0 <= y < self.h:
                    d.text((c * self.cell, y), self.rng.choice(GLYPHS), font=self.fnt,
                           fill=(170, 255, 190))
            if self.heads[c] > self.h + self.rng.uniform(0, self.h):
                self.heads[c] = self.rng.uniform(-60, 0)
                self.speed[c] = self.rng.uniform(60, 160)
        return self.img


class MatrixSaver(Saver):
    name, label = "matrix", N_("Matrix")

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._rain = _Rain(self.rng, WIDTH, HEIGHT, 15)
        self._wheel_rain = _Rain(self.rng, WHEEL_SIZE, WHEEL_SIZE, 15)

    def frame(self, t: float) -> Frame:
        img = self._rain.step(t).copy()
        green = np.asarray(img, dtype=np.uint16)
        green[..., 0] = green[..., 0] // 3
        green[..., 2] = green[..., 2] // 2
        img = Image.fromarray(green.astype(np.uint8), "RGB")
        wheel = to_round(self._wheel_rain.step(t))
        leds = {code: (0, self.rng.randrange(40, 255), self.rng.randrange(0, 40))
                for code in LED_CODES}
        return Frame(img, wheel, leds)
