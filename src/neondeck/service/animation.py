"""Takt der Animationen am Geraet: Bildschirmschoner und animierter Geraete-Look.

Die Engine schaltet sie ein und aus (``on_saver``/``on_animate``) und sagt bei jedem Bild,
wie lange bis zum naechsten (``saver_frame``/``look_frame``). Je Animation ein Einmal-Timer
im GUI-Thread; die Engine kommt mit ``attach`` dazu (sie schaltet den Look schon beim Anlegen
ein, die Timer muessen also vorher da sein).
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from ..ui.poster import QtPoster

if TYPE_CHECKING:
    from ..engine import Engine


class _FrameTimer:
    """Einmal-Timer: ``frame()`` zeichnet ein Bild und liefert die Wartezeit (``None``:
    Ende); weiter nur, solange ``running()``."""

    def __init__(self, run: Callable[[Callable[[], None]], None]) -> None:
        self.frame: Callable[[], float | None] = lambda: None
        self.running: Callable[[], bool] = lambda: False
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(partial(run, self._step))

    def set_active(self, active: bool) -> None:
        if active:
            self._timer.start(0)
        else:
            self._timer.stop()

    def _step(self) -> None:
        delay = self.frame()
        if delay is not None and self.running():
            self._timer.start(max(1, round(delay * 1000)))


class AnimationTimers:
    """``poster.run`` schuetzt jeden Schritt (Ausnahmen nur ins Log)."""

    def __init__(self, poster: QtPoster) -> None:
        self._saver = _FrameTimer(poster.run)
        self._look = _FrameTimer(poster.run)

    def attach(self, engine: Engine) -> None:
        self._saver.frame, self._saver.running = engine.saver_frame, lambda: engine.saver_active
        self._look.frame, self._look.running = engine.look_frame, lambda: engine.animating

    def on_saver(self, active: bool) -> None:
        self._saver.set_active(active)

    def on_animate(self, active: bool) -> None:
        self._look.set_active(active)

    def stop(self) -> None:
        self._saver.set_active(False)
        self._look.set_active(False)
