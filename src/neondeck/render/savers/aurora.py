"""Aurora: ruhige, fliessende Farbflaechen mit schlichter Uhr (zum Neutral-Theme)."""
from __future__ import annotations

from datetime import datetime

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ...core.i18n import N_
from ...device.layout import WHEEL_SIZE
from ..draw import to_round
from ..palette import hex_rgb
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver
from .tiles import MinuteCache, clock_digits, date_tiles, tile_texts


class AuroraSaver(Saver):
    name, label = "aurora", N_("Aurora")
    LOW = (120, 68)  # Rechenaufloesung, danach weich hochskaliert

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        w, h = self.LOW
        self._x, self._y = np.meshgrid(np.linspace(0, 4, w), np.linspace(0, 2.3, h))
        wx = np.linspace(0, 2, 60)
        self._wx, self._wy = np.meshgrid(wx, wx)
        self._palette = np.array([hex_rgb("#16181d"), hex_rgb("#1e2a4a"), hex_rgb("#4f8cff"),
                                  hex_rgb("#3ecf8e"), hex_rgb("#e6e8ee")], dtype=np.float32)
        self._clock = MinuteCache(self._clock_layer)

    @staticmethod
    def _clock_layer(now: datetime) -> Image.Image:
        """Reihe 2: HH MM, Reihe 3: Datum, je Feld (als Maske)."""
        white, soft = (255, 255, 255), (190, 196, 210)
        layer = ImageChops.add(tile_texts(clock_digits(now, 1, 80, white, "Inter", False)),
                               tile_texts(date_tiles(now, 2, 28, soft, "Inter", upper=False)))
        return layer.convert("L")

    def _field(self, x, y, t: float) -> np.ndarray:
        v = (np.sin(x * 1.3 + t * 0.35) + np.sin(y * 2.1 - t * 0.27)
             + np.sin((x + y) * 0.9 + t * 0.21) + np.sin(np.hypot(x - 2, y - 1.1) * 2 - t * 0.5))
        return (v + 4) / 8  # 0 … 1

    def _colorize(self, v: np.ndarray) -> np.ndarray:
        p = self._palette
        pos = np.clip(v, 0, 0.999) * (len(p) - 1) * 0.8  # oberstes Weiss nur angedeutet
        i = pos.astype(int)
        f = (pos - i)[..., None]
        return (p[i] * (1 - f) + p[np.minimum(i + 1, len(p) - 1)] * f).astype(np.uint8)

    def frame(self, t: float) -> Frame:
        low = Image.fromarray(self._colorize(self._field(self._x, self._y, t)), "RGB")
        img = low.resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC)
        now = self._now()
        img.paste((240, 242, 248), (0, 0), self._clock.get(now))
        wl = Image.fromarray(self._colorize(self._field(self._wx, self._wy, t + 3)), "RGB")
        wheel_img = wl.resize((WHEEL_SIZE, WHEEL_SIZE), Image.Resampling.BICUBIC)
        d = ImageDraw.Draw(wheel_img)
        sweep = now.second * 6
        d.arc((14, 14, WHEEL_SIZE - 14, WHEEL_SIZE - 14), -90, -90 + sweep, fill=(230, 232, 238), width=4)
        wheel = to_round(wheel_img)
        leds = {}
        for i, code in enumerate(LED_CODES):
            v = float(self._field(np.array(i * 0.5), np.array(1.0), t))
            leds[code] = tuple(int(c) for c in self._colorize(np.array([v]))[0])
        return Frame(img, wheel, leds)
