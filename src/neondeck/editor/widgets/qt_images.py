"""PIL-Bilder (wie das Geraet sie bekommt) als QImage fuer die Oberflaeche."""
from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage


def to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888).copy()
