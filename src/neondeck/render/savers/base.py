"""Grundlagen der Bildschirmschoner: ``Frame`` und die Basisklasse ``Saver``."""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from PIL import Image

from ...device.layout import DISPLAY_HEIGHT, ROUND_CODES, SURFACE_WIDTH
from ..palette import RGB

WIDTH, HEIGHT = SURFACE_WIDTH, DISPLAY_HEIGHT  # links + Mitte + rechts
LED_CODES = ROUND_CODES  # runde Tasten mit LED


@dataclass
class Frame:
    canvas: Image.Image                 # 480 × 270, RGB
    wheel: Image.Image                  # 240 × 240, RGB
    leds: dict[int, RGB] = field(default_factory=dict)
    changed: bool = True  # False: wie das letzte Bild – nichts senden


class SaverOptions(TypedDict, total=False):
    """Einstellungen einer Variante (heute nur die Diashow)."""
    folder: str
    slide_s: int


class Saver(ABC):
    name = ""
    label = ""

    def __init__(self, seed: int | None = None,
                 clock: Callable[[], float] = time.time,
                 options: SaverOptions | None = None) -> None:
        self.rng = random.Random(seed)
        self.clock = clock
        self.options: SaverOptions = options or {}

    @abstractmethod
    def frame(self, t: float) -> Frame:  # t: Sekunden seit Start
        ...

    def close(self) -> None:  # noqa: B027  # bewusst leer: Standard "nichts zu beenden"
        """Beim Beenden (Hintergrundarbeit abbrechen)."""

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.clock())
