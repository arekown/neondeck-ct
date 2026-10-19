"""Mitte im Cockpit-Look: Raster mit Scanlines, Scan-Linie, Neonrahmen je Feld.

Je belegtem Feld ein abgeschraegter Neonrahmen mit Verlauf Cyan ↔ Magenta (wandert langsam
ueber alle Felder), Gluehen um den Rahmen und Eck-Akzenten; das Tastenbild liegt im Rahmen.
Schwarzer Tastenhintergrund (``#000000``) ist durchsichtig, andere Farben bleiben deckend.
Zufaellige Kachel-Pings lassen den *Rahmen* Magenta aufblitzen (nie den Inhalt). Leere Felder:
gedimmter Rahmen, dezenter Datenstrom und Funkeln. Gedrueckt: Rahmen und Fuellung Magenta;
Fehler: rot.

**Raster beachten:** Schrift bleibt in ihrem Feld (Stege); Grafik darf durchlaufen.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ...device.layout import CENTER_WIDTH as CENTER_W
from ...device.layout import DISPLAY_HEIGHT as CENTER_H
from ...device.layout import FIELD_SIZE as TILE
from ..draw import bevel, draw_page_dots, mix, pulse, scale
from ..fonts import font
from ..palette import C_BG, C_CYAN, C_CYAN_DIM, C_MAGENTA, ERROR
from . import timing
from .timing import FIELDS, FPS

PRESSED, FAILED = "pressed", "error"
FRAME_INSET = 3         # Neonrahmen: Abstand zum Feldrand
FRAME_CUT = 12          # abgeschraegte Ecken
FRAME_ALPHA = 230       # Rahmen im Verlauf: nie ganz so kraeftig wie „gedrueckt“
ACCENT_LEN = 11         # Eck-Akzente (L-Winkel) an den nicht abgeschraegten Ecken
GLOW_RADIUS = 2.0       # Gluehen um den Rahmen (bleibt innen < 5 px vom Rahmen)
GLOW_LEVELS = 4         # Gluehen pulsiert in so vielen Stufen
GRID = 30               # Rasterweite der Mitte
SCANLINE_EVERY = 3      # jede dritte Zeile etwas dunkler (Monitor-Scanlines)
SCAN_PX_S = 40          # Scan-Linie: Pixel je Sekunde
SCAN_TAIL = 14
PULSE_S = 4.0           # Pulsieren von Raster und Gluehen
GRADIENT_P = 360        # Verlauf Cyan ↔ Magenta: Periode in Pixeln (schraeg)
GRADIENT_PX_S = 18      # … wandert so viele Pixel je Sekunde
EMPTY_DIM = 0.32        # leere Felder: Rahmen gedimmt
PING_LEVELS = 8
STREAM_ROW = 11         # Datenstrom in leeren Feldern: Zeilenhoehe
STREAM_ROWS = 48
STREAM_W, STREAM_H = 30, 56  # Fenster je leerem Feld (mittig, im Rahmen)
STREAM_PX = 4           # Datenstrom: Pixel je Bild
SPARKS = 3              # Funken je Bild (nur in leeren Feldern)


@dataclass(frozen=True)
class CenterTile:
    """Ein belegtes Feld der Mitte: fertiges Tastenbild (90 × 90, ohne Blitzrand),
    ``transparent`` bei schwarzem Hintergrund, ``state`` ``""``, ``PRESSED`` oder ``FAILED``."""
    image: Image.Image
    transparent: bool
    state: str = ""


def _local_box() -> tuple[int, int, int, int]:
    """Rahmen eines Felds in Feldkoordinaten (0–89)."""
    return FRAME_INSET, FRAME_INSET, TILE - 1 - FRAME_INSET, TILE - 1 - FRAME_INSET


def _field_box(i: int) -> tuple[int, int, int, int]:
    x0, y0 = (i % 4) * TILE, (i // 4) * TILE
    a, b, c, d = _local_box()
    return x0 + a, y0 + b, x0 + c, y0 + d


def _scaled(mask: Image.Image, k: float) -> Image.Image:
    return mask.point(lambda v: round(v * k))


def _gradient(width: int, height: int, strength: float) -> Image.Image:
    """Schraeger Verlauf Cyan → Magenta → Cyan (Periode ``GRADIENT_P``), mit ``strength``
    auf den Hintergrund gemischt."""
    x = np.arange(width)[None, :]
    y = np.arange(height)[:, None]
    k = 0.5 - 0.5 * np.cos(2 * np.pi * (x + 0.6 * y) / GRADIENT_P)
    cyan, magenta, bg = (np.array(c, float) for c in (C_CYAN, C_MAGENTA, C_BG))
    rgb = cyan + (magenta - cyan) * k[..., None]
    rgb = bg + (rgb - bg) * strength
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def _grid_image(k: float) -> Image.Image:
    img = Image.new("RGB", (CENTER_W, CENTER_H), C_BG)
    d = ImageDraw.Draw(img)
    line = mix(C_BG, C_CYAN, k)
    dark = scale(C_BG, 0.55)
    for y in range(0, CENTER_H, SCANLINE_EVERY):  # Scanlines
        d.line((0, y, CENTER_W, y), fill=dark)
    for x in range(0, CENTER_W, GRID):
        d.line((x, 0, x, CENTER_H), fill=line)
    for y in range(0, CENTER_H, GRID):
        d.line((0, y, CENTER_W, y), fill=line)
    return img


def _stream_image() -> tuple[Image.Image, Image.Image]:
    """Datenstrom fuer leere Felder: Spalte aus Hex-Zeilen (zweimal untereinander, damit
    das Fenster umlaufen kann) und ihre Helligkeit als Maske."""
    rng = random.Random(4242)
    h = STREAM_ROWS * STREAM_ROW
    img = Image.new("RGB", (STREAM_W, 2 * h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = font(10, False, "Share Tech Mono")
    for n in range(STREAM_ROWS):
        text = "".join(rng.choice("0123456789ABCDEF") for _ in range(4))
        color = mix(C_BG, C_MAGENTA, 0.5) if n % 7 == 0 else mix(C_BG, C_CYAN, 0.4)
        for off in (0, h):
            d.text((STREAM_W / 2, off + n * STREAM_ROW + STREAM_ROW / 2), text, font=fnt,
                   fill=color, anchor="mm")
    mask = img.convert("L").point(lambda v: min(255, v * 3))
    return img, mask


def _stream_fade() -> Image.Image:
    fade = np.minimum(1.0, np.minimum(np.arange(STREAM_H), STREAM_H - 1 -
                                      np.arange(STREAM_H)) / 14)
    return Image.fromarray(np.repeat((255 * fade)[:, None], STREAM_W, axis=1).astype(np.uint8),
                           "L")


@dataclass(frozen=True)
class _Masks:
    """Formen eines Felds (90 × 90, Maske ``L``), einmal vorgerechnet."""
    clip: Image.Image                # Tastenbild in Rahmenform (Ecken abgeschraegt)
    outline: Image.Image             # Rahmen + Eck-Akzente
    empty_outline: Image.Image       # Rahmen leerer Felder
    glow: list[Image.Image]          # Gluehen, pulsierend in ``GLOW_LEVELS`` Stufen
    pings: list[Image.Image]         # Rahmen im Ping, abklingend
    ping_glow: list[Image.Image]


def _polygon_mask(pts, **kw) -> Image.Image:
    mask = Image.new("L", (TILE, TILE), 0)
    ImageDraw.Draw(mask).polygon(pts, **kw)
    return mask


def _build_masks() -> _Masks:
    box = _local_box()
    x0, y0, x1, y1 = box
    pts = bevel(*box, FRAME_CUT)
    outline = _polygon_mask(pts, outline=FRAME_ALPHA)
    od = ImageDraw.Draw(outline)
    for line in (((x1 - ACCENT_LEN, y0), (x1, y0), (x1, y0 + ACCENT_LEN)),
                 ((x0, y1 - ACCENT_LEN), (x0, y1), (x0 + ACCENT_LEN, y1))):
        od.line(line, fill=255, width=2)
    glow = _polygon_mask(pts, outline=255, width=3).filter(ImageFilter.GaussianBlur(GLOW_RADIUS))
    inner = Image.new("L", (TILE, TILE), 255)  # innen ab 5 px vom Rahmen: kein Gluehen
    ImageDraw.Draw(inner).polygon(bevel(x0 + 5, y0 + 5, x1 - 5, y1 - 5, FRAME_CUT - 2), fill=0)
    glow = ImageChops.multiply(glow, inner)
    return _Masks(
        clip=_polygon_mask(pts, fill=255), outline=outline,
        empty_outline=_polygon_mask(pts, outline=255),
        glow=[_scaled(glow, 0.45 + 0.35 * n / (GLOW_LEVELS - 1)) for n in range(GLOW_LEVELS)],
        pings=[_scaled(outline, (n + 1) / PING_LEVELS) for n in range(PING_LEVELS)],
        ping_glow=[_scaled(glow, 0.8 * (n + 1) / PING_LEVELS) for n in range(PING_LEVELS)])


@dataclass
class _Pass:
    """Was ein Bild der Mitte gemeinsam hat (Zeit, Verlaufsversatz, Zeichenflaeche)."""
    img: Image.Image
    draw: ImageDraw.ImageDraw
    frame: int
    level: int       # Stufe des Gluehens
    grad_x: int      # Verlaufsversatz
    pings: dict[int, float]


class CenterRenderer:
    """Mitte (360 × 270) im Cockpit-Look. Nur im Engine-Thread benutzen (Cache je Tastenbild)."""

    def __init__(self) -> None:
        self._grid = (_grid_image(0.06), _grid_image(0.13))
        self._masks = _build_masks()
        # Verlaeufe: breiter als die Mitte, je Bild verschoben ausgeschnitten
        self._grad = _gradient(CENTER_W + GRADIENT_P, CENTER_H, 1.0)
        self._grad_dim = _gradient(CENTER_W + GRADIENT_P, CENTER_H, EMPTY_DIM)
        self._stream, self._stream_mask = _stream_image()
        self._stream_fade = _stream_fade()
        self._layers: dict[int, tuple[Image.Image, Image.Image, Image.Image]] = {}

    def background(self, frame: int) -> Image.Image:
        """Raster (pulsierend, mit Scanlines) und Scan-Linie mit Schweif."""
        t = frame / FPS
        img = Image.blend(self._grid[0], self._grid[1], pulse(t, PULSE_S))
        d = ImageDraw.Draw(img)
        span = CENTER_H + 4 * SCAN_TAIL
        y = (t * SCAN_PX_S) % span - 2 * SCAN_TAIL
        for k in range(SCAN_TAIL):
            yy = int(y - k * 2)
            if 0 <= yy < CENTER_H:
                head = mix(C_CYAN, C_MAGENTA, 0.35) if k == 0 else C_CYAN
                d.line((0, yy, CENTER_W - 1, yy), fill=mix(C_BG, head, 0.5 * (1 - k / SCAN_TAIL)))
        return img

    def render(self, tiles: list[CenterTile | None], page_index: int, page_count: int,
               frame: int) -> Image.Image:
        """Mittleres Display (360 × 270) zur Bildnummer ``frame``."""
        t = frame / FPS
        img = self.background(frame)
        pings: dict[int, float] = {}
        for i, k in timing.ping_tiles(frame):
            pings[i] = max(k, pings.get(i, 0.0))
        p = _Pass(img, ImageDraw.Draw(img), frame,
                  min(GLOW_LEVELS - 1, int(pulse(t, PULSE_S) * GLOW_LEVELS)),
                  int(GRADIENT_P - (t * GRADIENT_PX_S) % GRADIENT_P) % GRADIENT_P, pings)
        used: set[int] = set()
        empty: list[int] = []
        for i in range(FIELDS):
            tile = tiles[i] if i < len(tiles) else None
            if tile is None:
                self._paint_empty(p, i)
                empty.append(i)
            else:
                self._paint_tile(p, i, tile)
                used.add(id(tile.image))
        self._layers = {k: v for k, v in self._layers.items() if k in used}
        self._sparks(p.draw, empty, frame)
        draw_page_dots(p.draw, CENTER_W, page_count, page_index, C_MAGENTA,
                       mix(C_BG, C_CYAN_DIM, 0.7))
        return img

    @staticmethod
    def _ping_level(p: _Pass, i: int) -> int | None:
        ping = p.pings.get(i)
        return None if ping is None else min(PING_LEVELS - 1, int(ping * PING_LEVELS))

    def _paint_empty(self, p: _Pass, i: int) -> None:
        """Leeres Feld: gedimmter Rahmen im Verlauf und Datenstrom (ein Ping blitzt trotzdem)."""
        x0, y0 = (i % 4) * TILE, (i // 4) * TILE
        p.img.paste(self._grad_dim.crop((p.grad_x + x0, y0, p.grad_x + x0 + TILE, y0 + TILE)),
                    (x0, y0), self._masks.empty_outline)
        h = STREAM_ROWS * STREAM_ROW
        top = h - (p.frame * STREAM_PX + i * 97) % h  # Strom laeuft nach unten
        box = (0, top, STREAM_W, top + STREAM_H)
        mask = ImageChops.multiply(self._stream_mask.crop(box), self._stream_fade)
        p.img.paste(self._stream.crop(box),
                    (x0 + (TILE - STREAM_W) // 2, y0 + (TILE - STREAM_H) // 2), mask)
        pl = self._ping_level(p, i)
        if pl is not None:
            p.img.paste(C_MAGENTA, (x0, y0, x0 + TILE, y0 + TILE), self._masks.pings[pl])

    def _paint_tile(self, p: _Pass, i: int, tile: CenterTile) -> None:
        """Belegtes Feld: Rahmen mit Gluehen, Tastenbild darin, Rahmen obenauf."""
        m = self._masks
        x0, y0 = (i % 4) * TILE, (i // 4) * TILE
        cell = (x0, y0, x0 + TILE, y0 + TILE)
        grad = (p.grad_x + x0, y0, p.grad_x + x0 + TILE, y0 + TILE)
        pts = bevel(*_field_box(i), FRAME_CUT)
        pl = self._ping_level(p, i)
        accent = {PRESSED: C_MAGENTA, FAILED: ERROR}.get(tile.state)
        if accent is not None:  # sofort sichtbar: Fuellung und Gluehen in der Farbe
            p.draw.polygon(pts, fill=mix(C_BG, accent, 0.45))
            p.img.paste(accent, cell, m.glow[-1])
        else:
            p.img.paste(self._grad.crop(grad), (x0, y0), m.glow[p.level])
            if pl is not None:
                p.img.paste(C_MAGENTA, cell, m.ping_glow[pl])
        rgb, mask = self._layer(tile)
        if accent is not None and not tile.transparent:  # deckend: leicht einfaerben
            rgb = Image.blend(rgb, Image.new("RGB", rgb.size, accent), 0.25)
        p.img.paste(rgb, (x0, y0), mask)
        if accent is not None:
            p.draw.polygon(pts, outline=accent, width=2)
            return
        p.img.paste(self._grad.crop(grad), (x0, y0), m.outline)
        if pl is not None:  # Ping: nur der Rahmen blitzt Magenta
            p.img.paste(C_MAGENTA, cell, m.pings[pl])

    def _layer(self, tile: CenterTile) -> tuple[Image.Image, Image.Image]:
        """Tastenbild (RGB) und Maske: Rahmenform, bei schwarzem Hintergrund zusaetzlich
        durchsichtig, wo das Bild schwarz ist (weicher Uebergang an Kanten). Je Bild einmal."""
        cached = self._layers.get(id(tile.image))
        if cached is not None and cached[0] is tile.image:
            return cached[1], cached[2]
        rgb = tile.image.convert("RGB")
        if rgb.size != (TILE, TILE):
            rgb = rgb.resize((TILE, TILE))
        mask = self._masks.clip
        if tile.transparent:
            peak = np.asarray(rgb, dtype=np.uint16).max(axis=2)
            alpha = Image.fromarray(np.minimum(255, peak * 4).astype(np.uint8), "L")
            mask = ImageChops.multiply(alpha, self._masks.clip)
        self._layers[id(tile.image)] = (tile.image, rgb, mask)
        return rgb, mask

    @staticmethod
    def _sparks(d: ImageDraw.ImageDraw, empty: list[int], frame: int) -> None:
        """Funkeln: wenige helle Punkte in leeren Feldern (abseits des Datenstroms)."""
        if not empty:
            return
        rng = random.Random(frame * 104729 + 7)
        for _ in range(SPARKS):
            i = rng.choice(empty)
            x0, y0 = (i % 4) * TILE, (i // 4) * TILE
            x = x0 + rng.choice((rng.randrange(10, 26), rng.randrange(64, 80)))
            y = y0 + rng.randrange(10, 80)
            c = mix(C_BG, C_MAGENTA if rng.random() < 0.35 else C_CYAN, rng.uniform(0.5, 0.9))
            d.point((x, y), fill=c)
            d.point([(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)], fill=mix(C_BG, c, 0.45))
