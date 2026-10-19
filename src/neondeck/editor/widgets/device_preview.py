"""Bilder der Geraetevorschau: Touch-Kacheln, Leisten und Rad, gezeichnet mit denselben
Funktionen wie in der Engine (``engine.painter``) – Bildgestaltung, Zustandsbild, Ordner-„Zurück“,
Sticky-Kacheln, Ebenen, Leistenmodus und Radanzeige. Werte, die erst am Geraet entstehen
(Leiste, Radbogen), zeigt die Vorschau mit ``PREVIEW_VALUE``."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from PIL import Image
from PySide6.QtGui import QImage

from ...core.assets import resolve
from ...device.layout import ROUND_CODES, SQUARE_CODES, TOUCH_BUTTONS, ControlKind, ControlRef
from ...engine import navigation_state as nav
from ...engine.navigation_state import BACK_TILE
from ...engine.painter import (
    BACK_ICON,
    action_label,
    back_spec,
    button_spec,
    encoder_label,
    image_spec,
    strip_image,
    strip_label,
    strip_section,
    wheel_picture,
)
from ...profile.model import STRIP_SYSTEM, Assignment, Profile, TouchPage, Workspace
from ...render import system_strip
from ...render.icons import load_icon
from ...render.images import TILE, WHEEL_TILE, TileSpec, back_arrow, render_tile
from .labels import assignment_label
from .qt_images import to_qimage

log = logging.getLogger(__name__)

IconLoader = Callable[[str, int], Image.Image | None]
PREVIEW_VALUE = 50  # Leiste (Balken) und Radbogen zeigen im Editor diesen Beispielwert
PREVIEW_SYSTEM = (PREVIEW_VALUE,) * 4  # Leiste „system“: CPU, RAM, GPU 1, GPU 2
STRIP_SECTIONS = 6


def _default_icon_loader(ref: str, size: int) -> Image.Image | None:
    return load_icon(ref, size, resolve)


def _render(spec: TileSpec, key: tuple) -> QImage:
    try:
        return to_qimage(render_tile(spec))
    except (ValueError, TypeError) as e:  # z. B. handbearbeitete, ungueltige Farbe
        log.warning("Kachel nicht darstellbar (%s): %s", key, e)
        return to_qimage(render_tile(TileSpec(text=spec.text)))


class DevicePreview:
    """Gezeigtes Profil/Arbeitsbereich/Seite und die daraus gezeichneten Bilder
    (``tiles``, ``strips``, ``wheel``); ``refresh`` nach jeder Aenderung."""

    def __init__(self, icon_loader: IconLoader | None = None) -> None:
        self._icon_loader = icon_loader or _default_icon_loader
        self._icons: dict[tuple, Image.Image | None] = {}
        self._tile_cache: dict[tuple, QImage] = {}
        self.profile: Profile | None = None
        self.workspace: Workspace | None = None
        self.page: TouchPage | None = None
        self.tiles: list[QImage | None] = [None] * TOUCH_BUTTONS
        self.strips: tuple[QImage | None, QImage | None] = (None, None)
        self.wheel: QImage | None = None

    def set_view(self, profile: Profile | None, workspace: Workspace | None,
                 page: TouchPage | None) -> None:
        self.profile, self.workspace, self.page = profile, workspace, page
        self.refresh()

    def refresh(self) -> None:
        now = datetime.now()
        self._refresh_tiles(now)
        self.strips = self._strip_images()
        self.wheel = to_qimage(self._wheel_image(now))

    def _refresh_tiles(self, now: datetime) -> None:
        cache: dict[tuple, QImage] = {}
        tiles: list[QImage | None] = []
        for i in range(TOUCH_BUTTONS):
            spec, key = self._tile_spec(i, now)
            if spec is None:
                tiles.append(None)
                continue
            cache[key] = self._tile_cache.get(key) or _render(spec, key)
            tiles.append(cache[key])
        self._tile_cache = cache
        self.tiles = tiles

    def _strip_images(self) -> tuple[QImage, QImage]:
        ws, page = self.workspace, self.page
        sections = []
        for i in range(STRIP_SECTIONS):
            enc = ws.encoders[i] if ws and i < len(ws.encoders) else None
            if enc is None:
                sections.append(("", None, None))
                continue
            sections.append(strip_section(strip_label(enc, page, i), None, enc.strip,
                                          PREVIEW_VALUE))
        strips = []
        for side, part in (("left", sections[:3]), ("right", sections[3:])):
            if ws is not None and ws.strip_mode(side) == STRIP_SYSTEM:
                strips.append(to_qimage(system_strip.classic(PREVIEW_SYSTEM)))
            else:
                strips.append(to_qimage(strip_image(part)))
        return strips[0], strips[1]

    def shown_assignment(self, index: int) -> Assignment | None:
        """Was Feld ``index`` der gezeigten Seite am Geraet zeigt: im Ordner Feld 1
        „Zurück“, auf normalen Seiten die Sticky-Kachel, sonst die Belegung der Seite."""
        return nav.shown_assignment(self.workspace, self.page, index)

    def is_sticky(self, index: int) -> bool:
        return nav.is_sticky(self.workspace, self.page, index)

    def _tile_spec(self, index: int, now: datetime) -> tuple[TileSpec | None, tuple]:
        a = self.shown_assignment(index)
        if a is None:
            return None, ()
        if a is BACK_TILE:
            return back_spec(self._icon(BACK_ICON, TILE)), ("back",)
        img = a.image
        icon = self._icon(img.icon, TILE) if img.icon else None
        spec = button_spec(a, img, icon, now)
        return spec, spec.key(img.icon if icon is not None else None)

    def _wheel_image(self, now: datetime) -> Image.Image:
        ws = self.workspace
        if ws is None:
            return wheel_picture("blank", "", now)
        wheel = ws.wheel
        spec = None
        if wheel.display == "image" and wheel.image is not None:
            img = wheel.image
            spec = image_spec(img, self._icon(img.icon, WHEEL_TILE) if img.icon else None)
        try:
            return wheel_picture(wheel.display, wheel.label, now,
                                 value=PREVIEW_VALUE if wheel.display == "arc" else None,
                                 spec=spec)
        except (ValueError, TypeError) as e:  # z. B. handbearbeitete, ungueltige Farbe
            log.warning("Rad nicht darstellbar: %s", e)
            return wheel_picture("blank", "", now)

    def _icon(self, ref: str, size: int) -> Image.Image | None:
        key = (ref, size)
        if key not in self._icons:
            self._icons[key] = back_arrow(size) if ref == BACK_ICON else \
                self._icon_loader(ref, size)
        return self._icons[key]

    def control_label(self, ref: ControlRef) -> str:
        """Kurzer Text des Elements (Tooltip, Beschriftung der Tasten ohne Display)."""
        p, ws = self.profile, self.workspace
        if ref.kind == ControlKind.TOUCH:
            return assignment_label(self.shown_assignment(ref.index))
        if ref.kind == ControlKind.ROUND and p:
            return assignment_label(p.round.get(ROUND_CODES[ref.index]))
        if ref.kind == ControlKind.SQUARE and p:
            return assignment_label(p.square.get(SQUARE_CODES[ref.index]))
        if ref.kind in (ControlKind.KNOB, ControlKind.STRIP) and ws:
            return encoder_label(ws.encoders[ref.index])
        if ref.kind == ControlKind.WHEEL and ws and ws.wheel.rotate:
            return action_label(ws.wheel.rotate)
        return ""
