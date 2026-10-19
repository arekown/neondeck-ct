"""Diashow: eigene Bilder aus einem Ordner (auch Unterordner), zufaellige Reihenfolge, weich
ueberblendet; das Rad zeigt einen runden Ausschnitt, die LEDs Farben des Bildes."""
from __future__ import annotations

import logging
import os
from concurrent.futures import Future, wait
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PIL import Image, ImageOps

from ...core.i18n import N_
from ...core.workers import Worker
from ...device.layout import WHEEL_SIZE
from ..draw import mix, scale, to_round
from ..palette import RGB
from .aurora import AuroraSaver
from .base import HEIGHT, LED_CODES, WIDTH, Frame, Saver

log = logging.getLogger(__name__)

IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"})
MAX_IMAGES = 10000
SLIDE_S = 10


def list_images(folder: Path, limit: int = MAX_IMAGES) -> list[Path]:
    """Bilddateien in ``folder`` samt Unterordnern (versteckte ausgelassen), hoechstens
    ``limit``."""
    out: list[Path] = []
    if not folder.is_dir():
        return out
    for root, dirs, files in os.walk(folder, onerror=lambda e: None):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if not name.startswith(".") and Path(name).suffix.lower() in IMAGE_EXT:
                out.append(Path(root) / name)
                if len(out) >= limit:
                    return out
    return out


@dataclass
class _Slide:
    canvas: Image.Image
    wheel: Image.Image
    leds: dict[int, RGB]


def _prepare(path: Path) -> _Slide:
    """Bild laden und auf die Flaeche zuschneiden (fuellend, mittig); im Hintergrund-Thread."""
    with Image.open(path) as src:
        src.draft("RGB", (WIDTH * 2, HEIGHT * 2))  # JPEG: gleich verkleinert dekodieren
        img = ImageOps.exif_transpose(src).convert("RGB")
    canvas = ImageOps.fit(img, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    wheel = to_round(ImageOps.fit(img, (WHEEL_SIZE, WHEEL_SIZE), Image.Resampling.LANCZOS))
    strip = canvas.resize((len(LED_CODES), 1), Image.Resampling.BOX)
    leds = {}
    for i, code in enumerate(LED_CODES):
        r, g, b = strip.getpixel((i, 0))
        k = 255 / max(r, g, b, 1)  # LEDs leuchten in der Farbe, nicht in der Helligkeit
        leds[code] = scale((r, g, b), min(k, 3.0))
    return _Slide(canvas, wheel, leds)


class SlideshowSaver(Saver):
    name, label = "diashow", N_("Diashow (eigene Bilder)")
    FADE_S = 1.2

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.folder = Path(str(self.options.get("folder") or "")).expanduser()
        try:
            self.slide_s = max(3, int(self.options.get("slide_s") or SLIDE_S))
        except (TypeError, ValueError):
            self.slide_s = SLIDE_S
        self.files = list_images(self.folder) if str(self.folder) not in ("", ".") else []
        self.rng.shuffle(self.files)
        self._pos = 0
        self._fallback: Saver | None = None
        if not self.files:
            log.warning("Diashow: keine Bilder in %r – stattdessen Aurora", str(self.folder))
            self._fallback = AuroraSaver(clock=self.clock)
        self._pool = Worker("diashow")
        self._current: _Slide | None = None
        self._next: Future | None = None
        self._shown_at = 0.0
        self._fade_from: _Slide | None = None
        self._fade_at = 0.0
        self._sent_static = False
        if self.files:
            self._next = self._load_next()

    def _load_next(self) -> Future:
        path = self.files[self._pos % len(self.files)]
        self._pos += 1
        if self._pos % len(self.files) == 0:
            self.rng.shuffle(self.files)
        return self._pool.submit(partial(_prepare, path))

    def _take(self, future: Future) -> _Slide | None:
        try:
            return future.result(timeout=0)
        except Exception as e:  # noqa: BLE001 - kaputtes Bild (jeder Lesefehler): naechstes
            log.warning("Diashow: Bild nicht lesbar: %s", e)
            return None

    def frame(self, t: float) -> Frame:
        if self._fallback is not None:
            return self._fallback.frame(t)
        if self._current is None:  # erstes Bild: kurz darauf warten
            wait([self._next], timeout=0.5)  # Fehler meldet ``_take``
        if self._next is not None and self._next.done() and (
                self._current is None or t - self._shown_at >= self.slide_s):
            slide = self._take(self._next)
            self._next = self._load_next()
            if slide is not None:
                self._fade_from, self._fade_at = self._current, t
                self._current, self._shown_at = slide, t
                self._sent_static = False
        cur = self._current
        if cur is None:
            return Frame(Image.new("RGB", (WIDTH, HEIGHT)), Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE)),
                         changed=not self._sent_static)
        k = (t - self._fade_at) / self.FADE_S
        if self._fade_from is not None and k < 1:
            old = self._fade_from
            leds = {c: mix(old.leds[c], cur.leds[c], k) for c in LED_CODES}
            return Frame(Image.blend(old.canvas, cur.canvas, k),
                         Image.blend(old.wheel, cur.wheel, k), leds)
        self._fade_from = None
        changed = not self._sent_static
        self._sent_static = True
        return Frame(cur.canvas, cur.wheel, cur.leds, changed=changed)

    def close(self) -> None:
        self._pool.shutdown(cancel=True)
