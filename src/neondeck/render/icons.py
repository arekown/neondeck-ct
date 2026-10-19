"""Tastensymbole laden: Datei (SVG ueber Qt, Rastergrafik ueber Pillow) oder Symbolthema.

Qt wird erst beim Laden eines SVG oder Theme-Symbols geholt; ohne laufende ``QGuiApplication``
legt dieses Modul eine an (der Dienst-Prozess hat dann keine eigene Oberflaeche).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

Resolver = Callable[[str], Path | None]


def _default_resolver(ref: str) -> Path | None:
    return Path(ref[5:]) if ref.startswith("file:") else None


def _qt_app():
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication([])
    return app


def _centered(img: Image.Image, size: int) -> Image.Image:
    """``img`` ins ``size`` x ``size`` grosse transparente Quadrat einpassen (mittig)."""
    img.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return out


def _from_qimage(qimg, size: tuple[int, int]) -> Image.Image:
    data = bytes(qimg.constBits())
    return Image.frombuffer("RGBA", size, data, "raw", "RGBA", qimg.bytesPerLine(), 1).copy()


def _load_svg(path: Path, size: int) -> Image.Image | None:
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _qt_app()
    renderer = QSvgRenderer(QByteArray(path.read_bytes()))
    if not renderer.isValid():
        return None
    ds = renderer.defaultSize()
    if ds.width() <= 0 or ds.height() <= 0:
        ds = renderer.viewBox().size()
    if ds.width() <= 0 or ds.height() <= 0:
        return None
    scale = size / max(ds.width(), ds.height())
    w, h = max(1, round(ds.width() * scale)), max(1, round(ds.height() * scale))
    qimg = QImage(size, size, QImage.Format_RGBA8888)
    qimg.fill(Qt.transparent)
    p = QPainter(qimg)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF((size - w) / 2, (size - h) / 2, w, h))
    p.end()
    return _from_qimage(qimg, (size, size))


def _load_raster(path: Path, size: int) -> Image.Image:
    with Image.open(path) as src:
        return _centered(src.convert("RGBA"), size)


def _load_theme(name: str, size: int) -> Image.Image | None:
    """Symbol ``name`` aus dem Symbolthema des Desktops (``QIcon.fromTheme``)."""
    from PySide6.QtGui import QIcon, QImage

    _qt_app()
    icon = QIcon.fromTheme(name)
    if icon.isNull():
        return None
    pix = icon.pixmap(size, size)
    if pix.isNull():
        return None
    qimg = pix.toImage().convertToFormat(QImage.Format_RGBA8888)
    img = _from_qimage(qimg, (qimg.width(), qimg.height()))
    # kleiner geliefert (oder HiDPI groesser): einpassen
    return img if img.size == (size, size) else _centered(img, size)


def load_icon(ref: str, size: int, resolver: Resolver | None = None) -> Image.Image | None:
    """Symbol als RGBA size x size; unbekannt/defekt -> None (nie eine Ausnahme).

    ``theme:<name>`` kommt aus dem Symbolthema des Desktops (App-Symbole der dynamischen
    Ordner), alles andere ueber ``resolver`` aus einer Datei."""
    try:
        if ref.startswith("theme:"):
            return _load_theme(ref[6:], size) if ref[6:] else None
        path = (resolver or _default_resolver)(ref)
        if path is None or not Path(path).is_file():
            return None
        path = Path(path)
        if path.suffix.lower() == ".svg":
            return _load_svg(path, size)
        return _load_raster(path, size)
    except Exception as e:  # noqa: BLE001  # jede kaputte Bilddatei: kein Bild statt Absturz
        log.debug("Symbol %r nicht ladbar: %s", ref, e)
        return None
